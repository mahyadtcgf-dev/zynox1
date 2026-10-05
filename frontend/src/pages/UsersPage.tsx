import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, Pencil } from 'lucide-react';
import { api } from '@/services/api';
import type { Paginated, RoleOut, User } from '@/types';
import { AppLayout, PageHeader } from '@/layouts/AppLayout';
import { Card } from '@/components/ui/Card';
import { Table, type Column } from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Field, Input, Select } from '@/components/ui/Field';
import { toast } from '@/stores/toast';
import { useAuthStore } from '@/stores/auth';
import { formatDateTime } from '@/utils/format';

export function UsersPage() {
  const queryClient = useQueryClient();
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<User | null>(null);
  const [creating, setCreating] = useState(false);

  const { data } = useQuery<Paginated<User>>({
    queryKey: ['users', page, search],
    queryFn: () =>
      api.get<Paginated<User>>('/api/v1/users', { page, page_size: 20, search: search || undefined }),
  });

  const { data: roles } = useQuery<RoleOut[]>({
    queryKey: ['roles'],
    queryFn: () => api.get<RoleOut[]>('/api/v1/users/roles/list'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/api/v1/users/${id}`),
    onSuccess: () => {
      toast.success('User deleted');
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (error: unknown) => toast.error('Delete failed', error instanceof Error ? error.message : undefined),
  });

  const columns: Column<User>[] = [
    {
      key: 'username',
      header: 'User',
      render: (row) => (
        <div>
          <p className="font-medium text-slate-100">{row.username}</p>
          <p className="text-xxs text-muted">{row.email}</p>
        </div>
      ),
    },
    {
      key: 'roles',
      header: 'Roles',
      render: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.roles.map((role) => (
            <Badge key={role} variant={role === 'admin' ? 'info' : 'neutral'}>
              {role}
            </Badge>
          ))}
        </div>
      ),
    },
    {
      key: 'mfa',
      header: 'MFA',
      render: (row) => (row.totp_enabled ? <Badge variant="success">Enabled</Badge> : <span className="text-muted">—</span>),
    },
    { key: 'lastLogin', header: 'Last login', render: (row) => formatDateTime(row.last_login_at) },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <Badge variant={row.is_active ? 'success' : 'danger'}>{row.is_active ? 'Active' : 'Disabled'}</Badge>,
    },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (row) => (
        <div className="flex items-center justify-end gap-1">
          {hasPermission('user:update') ? (
            <button
              title="Edit"
              onClick={() => setEditing(row)}
              className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-base-700 hover:text-slate-200"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
          ) : null}
          {hasPermission('user:delete') ? (
            <button
              title="Delete"
              onClick={() => {
                if (confirm(`Delete user "${row.username}"? This cannot be undone.`)) {
                  deleteMutation.mutate(row.id);
                }
              }}
              className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-red-500/10 hover:text-red-400"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <AppLayout>
      <PageHeader
        title="Users"
        description="Panel accounts and their assigned roles"
        actions={
          hasPermission('user:create') ? (
            <Button variant="primary" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" />
              New user
            </Button>
          ) : null
        }
      />

      <Card>
        <div className="border-b border-base-700 p-4">
          <Input
            type="search"
            placeholder="Search users…"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <Table
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(row) => row.id}
          empty="No users found."
        />
        <div className="flex items-center justify-between border-t border-base-700 px-4 py-3 text-xs text-muted">
          <span>{data?.total ?? 0} total</span>
          <div className="flex items-center gap-2">
            <Button size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </Button>
            <span className="font-mono">{page}</span>
            <Button size="sm" disabled={(data?.pages ?? 1) <= page} onClick={() => setPage(page + 1)}>
              Next
            </Button>
          </div>
        </div>
      </Card>

      {creating || editing ? (
        <UserFormModal user={editing} roles={roles ?? []} onClose={() => { setCreating(false); setEditing(null); }} />
      ) : null}
    </AppLayout>
  );
}

function UserFormModal({
  user,
  roles,
  onClose,
}: {
  user: User | null;
  roles: RoleOut[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState(user?.username ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [password, setPassword] = useState('');
  const [selectedRoles, setSelectedRoles] = useState<string[]>(user?.roles ?? ['viewer']);

  const mutation = useMutation({
    mutationFn: () => {
      const payload = { email, roles: selectedRoles, is_active: true };
      if (user) {
        return api.patch(`/api/v1/users/${user.id}`, { ...payload, password: password || undefined });
      }
      return api.post('/api/v1/users', { username, ...payload, password });
    },
    onSuccess: () => {
      toast.success(user ? 'User updated' : 'User created');
      queryClient.invalidateQueries({ queryKey: ['users'] });
      onClose();
    },
    onError: (error: unknown) => toast.error('Save failed', error instanceof Error ? error.message : undefined),
  });

  return (
    <Modal open onClose={onClose} title={user ? 'Edit user' : 'New user'} size="md">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
        className="space-y-4"
      >
        <Field label="Username">
          <Input value={username} disabled={!!user} onChange={(e) => setUsername(e.target.value)} required />
        </Field>
        <Field label="Email">
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </Field>
        <Field label={user ? 'New password (optional)' : 'Password'} hint="Minimum 10 characters, 3 character classes.">
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required={!user} />
        </Field>
        <Field label="Roles">
          <Select
            multiple
            value={selectedRoles}
            onChange={(event) =>
              setSelectedRoles(Array.from(event.target.selectedOptions).map((option) => option.value))
            }
            className="h-24"
          >
            {roles.map((role) => (
              <option key={role.name} value={role.name}>
                {role.name} — {role.description ?? role.permissions.length} permissions
              </option>
            ))}
          </Select>
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
