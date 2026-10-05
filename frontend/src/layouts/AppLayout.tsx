import { type ReactNode, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Server,
  Users,
  HardDrive,
  Send,
  ScrollText,
  Settings,
  LogOut,
  Search,
  Menu,
  X,
  FileCog,
} from 'lucide-react';
import { clsx } from 'clsx';
import { useAuthStore } from '@/stores/auth';
import { useToastStore } from '@/stores/toast';

interface NavItem {
  path: string;
  label: string;
  icon: typeof LayoutDashboard;
  permission?: string;
}

const NAV: NavItem[] = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/services', label: 'Services', icon: Server, permission: 'service:view' },
  { path: '/configurations', label: 'Configurations', icon: FileCog, permission: 'config:view' },
  { path: '/users', label: 'Users', icon: Users, permission: 'user:view' },
  { path: '/servers', label: 'Servers', icon: HardDrive, permission: 'server:view' },
  { path: '/telegram', label: 'Telegram', icon: Send, permission: 'telegram:view' },
  { path: '/logs', label: 'Logs', icon: ScrollText, permission: 'log:view' },
  { path: '/settings', label: 'Settings', icon: Settings, permission: 'setting:view' },
];

export function AppLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const pushToast = useToastStore((state) => state.push);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const visibleNav = NAV.filter((item) => !item.permission || user?.permissions.includes(item.permission));

  const handleLogout = async () => {
    await logout();
    pushToast({ title: 'Signed out', variant: 'info' });
    navigate('/login');
  };

  return (
    <div className="flex h-screen overflow-hidden bg-base-950">
      {/* Sidebar */}
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-40 w-60 border-r border-base-800 bg-base-900 transition-transform',
          'lg:static lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex h-16 items-center gap-2.5 border-b border-base-800 px-5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-600/15 ring-1 ring-accent-600/30">
            <span className="text-xs font-bold text-accent-400">Z</span>
          </div>
          <span className="text-sm font-semibold tracking-tight text-slate-100">Zynox</span>
          <button
            onClick={() => setSidebarOpen(false)}
            className="ml-auto text-slate-500 lg:hidden"
            aria-label="Close sidebar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex flex-col gap-0.5 p-3">
          {visibleNav.map((item) => {
            const active =
              location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                className={clsx(
                  'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors',
                  active
                    ? 'bg-base-800 font-medium text-slate-100'
                    : 'text-slate-400 hover:bg-base-850 hover:text-slate-200'
                )}
              >
                <Icon className="h-4 w-4 flex-shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="absolute inset-x-0 bottom-0 border-t border-base-800 p-3">
          <div className="rounded-lg px-3 py-2">
            <p className="truncate text-xs font-medium text-slate-300">{user?.username}</p>
            <p className="mt-0.5 truncate text-xxs text-muted">
              {user?.roles.join(', ')}
            </p>
          </div>
          <button
            onClick={handleLogout}
            className="mt-1 flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-base-850 hover:text-slate-200"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>

      {sidebarOpen ? (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      ) : null}

      {/* Main */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-16 items-center gap-4 border-b border-base-800 bg-base-900/60 px-6">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-slate-400 lg:hidden"
            aria-label="Open sidebar"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="relative hidden flex-1 max-w-md sm:block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
            <input
              type="search"
              placeholder="Search…"
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  navigate(`/configurations?search=${encodeURIComponent(event.currentTarget.value)}`);
                }
              }}
              className="h-9 w-full rounded-lg border border-base-700 bg-base-850 pl-9 pr-3 text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
            />
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-xxs text-muted sm:block">{user?.email}</span>
            <div className="h-7 w-7 rounded-full bg-base-700 text-center text-xs font-semibold leading-7 text-slate-300">
              {user?.username.charAt(0).toUpperCase()}
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-6 py-6">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-slate-100">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
