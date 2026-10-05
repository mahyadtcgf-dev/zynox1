"""User management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import client_ip, require_permission
from app.models import Role, User
from app.schemas.common import MessageOut, Paginated, PaginationParams, validate_sort_field
from app.schemas.user import (
    RoleOut,
    UserCreateIn,
    UserListItem,
    UserOut,
    UserUpdateIn,
)
from app.services import audit_service
from app.services.auth_service import make_password_hash

router = APIRouter(prefix="/users", tags=["users"])

USER_SORTABLE = {"created_at", "username"}


async def _resolve_roles(db: AsyncSession, names: list[str]) -> list[Role]:
    stmt = select(Role).where(Role.name.in_(names))
    roles = list((await db.execute(stmt)).scalars().all())
    found = {r.name for r in roles}
    missing = set(names) - found
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown roles: {', '.join(sorted(missing))}",
        )
    return roles


def _to_list_item(user: User) -> UserListItem:
    return UserListItem(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        roles=[r.name for r in user.roles],
    )


@router.get("", response_model=Paginated[UserListItem])
@router.get("/", response_model=Paginated[UserListItem], include_in_schema=False)
async def list_users(
    db: AsyncSession = Depends(get_db),
    params: PaginationParams = Depends(),
    _user: User=Depends(require_permission("user:view")),
) -> Paginated[UserListItem]:
    conditions = []
    if params.search:
        conditions.append(User.username.ilike(f"%{params.search}%"))

    total = await db.scalar(select(func.count()).select_from(User).where(*conditions))
    validate_sort_field(params.sort_by, USER_SORTABLE)
    order_col = User.created_at
    if params.sort_by == "username":
        order_col = User.username  # type: ignore[assignment]
    order = order_col.desc() if params.sort_order == "desc" else order_col.asc()

    stmt = (
        select(User)
        .where(*conditions)
        .order_by(order, User.id.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().unique().all()
    return Paginated.build(
        items=[_to_list_item(r) for r in rows],
        total=int(total or 0),
        page=params.page,
        page_size=params.page_size,
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    payload: UserCreateIn,
    db: AsyncSession = Depends(get_db),
    actor: User=Depends(require_permission("user:create")),
) -> UserOut:
    existing = (
        await db.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    roles = await _resolve_roles(db, payload.roles)
    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=make_password_hash(payload.password),
        is_active=payload.is_active,
        roles=roles,
    )
    db.add(user)
    await db.flush()
    await audit_service.log_action(
        db,
        action="user.create",
        resource_type="user",
        resource_id=str(user.id),
        details={"username": user.username, "roles": [r.name for r in roles]},
        actor=actor,
        ip_address=client_ip(request),
    )
    await db.commit()
    return UserOut.from_user(user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User=Depends(require_permission("user:view")),
) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.from_user(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    request: Request,
    user_id: uuid.UUID,
    payload: UserUpdateIn,
    db: AsyncSession = Depends(get_db),
    actor: User=Depends(require_permission("user:update")),
) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    data = payload.model_dump(exclude_unset=True)
    if "password" in data and data["password"]:
        user.password_hash = make_password_hash(data.pop("password"))
    if "roles" in data and data["roles"]:
        user.roles = await _resolve_roles(db, data.pop("roles"))
    for key, value in data.items():
        setattr(user, key, value)

    await db.flush()
    await audit_service.log_action(
        db,
        action="user.update",
        resource_type="user",
        resource_id=str(user.id),
        details={
            k: v
            for k, v in payload.model_dump(exclude_unset=True).items()
            if k != "password"
        },
        actor=actor,
        ip_address=client_ip(request),
    )
    await db.commit()
    return UserOut.from_user(user)


@router.delete("/{user_id}", response_model=MessageOut)
async def delete_user(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User=Depends(require_permission("user:delete")),
) -> MessageOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot be deleted",
        )
    username = user.username
    await db.delete(user)
    await audit_service.log_action(
        db,
        action="user.delete",
        resource_type="user",
        resource_id=str(user_id),
        details={"username": username},
        actor=actor,
        ip_address=client_ip(request),
    )
    await db.commit()
    return MessageOut(message="User deleted")


@router.get("/roles/list", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _user: User=Depends(require_permission("user:view")),
) -> list[RoleOut]:
    stmt = select(Role).order_by(Role.name)
    rows = (await db.execute(stmt)).scalars().all()
    return [RoleOut.from_role(r) for r in rows]
