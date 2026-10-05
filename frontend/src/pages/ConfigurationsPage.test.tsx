import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigurationsPage } from '@/pages/ConfigurationsPage';
import { useAuthStore } from '@/stores/auth';
import * as apiModule from '@/services/api';

const CONFIG = {
  id: '22222222-2222-2222-2222-222222222222',
  name: 'client-01',
  uuid: 'b8dd95b7-3f4a-4e0d-9f3f-1c1c1c1c1c1c',
  protocol: 'vless' as const,
  transport: 'tcp' as const,
  host: 'edge01.example.com',
  share_url: 'vless://b8dd95b7@edge01.example.com:443?type=tcp&security=tls',
  enabled: true,
  expires_at: null,
  created_at: '2026-01-01T00:00:00Z',
  service_id: null,
};

const ADMIN = {
  id: '33333333-3333-3333-3333-333333333333',
  username: 'admin',
  email: 'admin@zynox.local',
  is_active: true,
  totp_enabled: false,
  created_at: '2026-01-01T00:00:00Z',
  roles: ['admin'],
  permissions: ['config:view', 'config:create', 'config:update', 'config:delete'],
};

const EMPTY = { items: [], total: 0, page: 1, page_size: 20, pages: 0 };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ConfigurationsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ConfigurationsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ user: ADMIN, initialized: true });
  });

  it('lists configurations', async () => {
    vi.spyOn(apiModule.api, 'get').mockResolvedValue({ ...EMPTY, items: [CONFIG], total: 1, pages: 1 } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('client-01')).toBeInTheDocument();
      expect(screen.getByText('edge01.example.com')).toBeInTheDocument();
    });
  });

  it('exposes a copy control for the share url', async () => {
    vi.spyOn(apiModule.api, 'get').mockResolvedValue({ ...EMPTY, items: [CONFIG], total: 1, pages: 1 } as never);

    renderPage();

    const button = await screen.findByRole('button', { name: /copy link/i });
    expect(button).toBeInTheDocument();
  });

  it('opens the generation wizard', async () => {
    vi.spyOn(apiModule.api, 'get').mockResolvedValue(EMPTY as never);

    renderPage();

    // The header button is the first one; the wizard's final-step button only
    // exists after the modal opens.
    const buttons = await screen.findAllByRole('button', { name: /^generate configuration$/i });
    fireEvent.click(buttons[0]);

    await waitFor(() => {
      expect(screen.getByText('Create a validated client configuration in a few steps.')).toBeInTheDocument();
    });
  });

  it('hides the generate button without permission', async () => {
    useAuthStore.setState({
      user: { ...ADMIN, permissions: ['config:view'] },
      initialized: true,
    });
    vi.spyOn(apiModule.api, 'get').mockResolvedValue(EMPTY as never);

    renderPage();

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /^generate configuration$/i })).not.toBeInTheDocument();
    });
  });

  it('shows an empty state', async () => {
    vi.spyOn(apiModule.api, 'get').mockResolvedValue(EMPTY as never);

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText('No configurations yet. Generate one to get started.')
      ).toBeInTheDocument();
    });
  });
});
