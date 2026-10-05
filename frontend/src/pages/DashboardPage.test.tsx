import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DashboardPage } from '@/pages/DashboardPage';
import * as apiModule from '@/services/api';

const STATS = {
  app_name: 'Zynox',
  services_total: 4,
  services_active: 3,
  services_offline: 1,
  services_disabled: 0,
  configs_total: 12,
  configs_active: 10,
  configs_expired: 1,
  users_total: 5,
  users_active: 4,
  servers_total: 2,
  servers_online: 2,
  telegram_bot_configured: true,
  telegram_authorized_users: 1,
  system: {
    cpu_percent: 12.5,
    memory_percent: 48.2,
    disk_percent: 66.8,
    network_rx_bps: 1024,
    network_tx_bps: 2048,
    uptime_seconds: 3600,
  },
  recent_activity: [
    {
      id: 'a1b2c3d4-0000-0000-0000-000000000001',
      actor_username: 'admin',
      actor_type: 'user',
      action: 'service.create',
      resource_type: 'service',
      status: 'success',
      created_at: new Date().toISOString(),
    },
  ],
};

function renderDashboard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders stat cards after loading', async () => {
    vi.spyOn(apiModule.api, 'get').mockResolvedValue(STATS as never);

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Services')).toBeInTheDocument();
    });
    expect(screen.getByText('Configurations')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
    expect(screen.getByText('Servers')).toBeInTheDocument();
  });

  it('shows system resource bars', async () => {
    vi.spyOn(apiModule.api, 'get').mockResolvedValue(STATS as never);

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('CPU')).toBeInTheDocument();
      expect(screen.getByText('Memory')).toBeInTheDocument();
      expect(screen.getByText('Disk')).toBeInTheDocument();
    });
  });

  it('shows recent activity rows', async () => {
    vi.spyOn(apiModule.api, 'get').mockResolvedValue(STATS as never);

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('service.create')).toBeInTheDocument();
    });
  });

  it('shows a retry control when the request fails', async () => {
    vi.spyOn(apiModule.api, 'get').mockRejectedValue(new Error('boom') as never);

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Failed to load dashboard data.')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });
});
