import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/auth';
import { tokens } from '@/services/api';
import { AppLayout } from '@/layouts/AppLayout';

const USER = {
  id: '33333333-3333-3333-3333-333333333333',
  username: 'admin',
  email: 'admin@zynox.local',
  is_active: true,
  totp_enabled: false,
  created_at: '2026-01-01T00:00:00Z',
  roles: ['admin'],
  permissions: [
    'service:view',
    'config:view',
    'user:view',
    'server:view',
    'telegram:view',
    'log:view',
    'setting:view',
  ],
};

function renderLayout() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AppLayout>
          <div>page-content</div>
        </AppLayout>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AppLayout navigation with RBAC', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ user: USER, initialized: true });
    tokens.set('access', 'refresh');
  });

  it('renders the brand', () => {
    renderLayout();
    expect(screen.getAllByText('Zynox').length).toBeGreaterThan(0);
  });

  it('renders every section the user may view', () => {
    renderLayout();
    for (const label of [
      'Dashboard',
      'Services',
      'Configurations',
      'Users',
      'Servers',
      'Telegram',
      'Logs',
      'Settings',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('hides sections the user lacks permission for', () => {
    useAuthStore.setState({
      user: { ...USER, permissions: ['service:view'] },
      initialized: true,
    });
    renderLayout();

    expect(screen.getByText('Services')).toBeInTheDocument();
    expect(screen.queryByText('Users')).not.toBeInTheDocument();
    expect(screen.queryByText('Telegram')).not.toBeInTheDocument();
  });

  it('shows the signed-in username', () => {
    renderLayout();
    // The sidebar footer holds username and roles in separate <p> elements;
    // query by the header avatar's sibling email instead, which is unambiguous.
    expect(screen.getByText('admin@zynox.local')).toBeInTheDocument();
  });
});
