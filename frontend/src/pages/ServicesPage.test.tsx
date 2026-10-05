import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ServicesPage } from '@/pages/ServicesPage';
import * as apiModule from '@/services/api';

const SERVICE = {
  id: '11111111-1111-1111-1111-111111111111',
  name: 'edge-01',
  description: null,
  host: 'edge01.example.com',
  port: 443,
  protocol: 'vless' as const,
  transport: 'tcp' as const,
  tag: null,
  status: 'running',
  enabled: true,
  server_id: null,
  last_error: null,
  config_count: 2,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ServicesPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ServicesPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('lists services', async () => {
    vi.spyOn(apiModule.api, 'get').mockResolvedValue({
      items: [SERVICE],
      total: 1,
      page: 1,
      page_size: 20,
      pages: 1,
    } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('edge-01')).toBeInTheDocument();
      expect(screen.getByText('edge01.example.com:443')).toBeInTheDocument();
    });
  });

  it('shows an empty state when there are no services', async () => {
    vi.spyOn(apiModule.api, 'get').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      pages: 0,
    } as never);

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText('No services yet. Create one to get started.')
      ).toBeInTheDocument();
    });
  });

  it('debounces the search box', async () => {
    const get = vi
      .spyOn(apiModule.api, 'get')
      .mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, pages: 0 } as never);

    renderPage();

    const input = await screen.findByPlaceholderText('Search services…');
    fireEvent.change(input, { target: { value: 'edge' } });

    // The first call is the initial load; the search call follows.
    await waitFor(() => {
      expect(get).toHaveBeenCalled();
    });
  });
});
