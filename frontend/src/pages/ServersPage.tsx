import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { Paginated, Server, SystemMetrics } from '@/types';
import { AppLayout, PageHeader } from '@/layouts/AppLayout';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Table, type Column } from '@/components/ui/Table';
import { StatusBadge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Field';
import { formatBitrate, formatDuration } from '@/utils/format';

export function ServersPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');

  const { data } = useQuery<Paginated<Server>>({
    queryKey: ['servers', page, search],
    queryFn: () =>
      api.get<Paginated<Server>>('/api/v1/servers', { page, page_size: 20, search: search || undefined }),
  });

  const { data: metrics } = useQuery<SystemMetrics>({
    queryKey: ['system-metrics'],
    queryFn: () => api.get<SystemMetrics>('/api/v1/system/metrics'),
    refetchInterval: 15_000,
  });

  const columns: Column<Server>[] = [
    {
      key: 'name',
      header: 'Server',
      render: (row) => (
        <div>
          <p className="font-medium text-slate-100">{row.name}</p>
          <p className="font-mono text-xxs text-muted">{row.address}</p>
        </div>
      ),
    },
    { key: 'location', header: 'Location', render: (row) => row.location ?? '—' },
    {
      key: 'resources',
      header: 'Resources',
      render: (row) => (
        <div className="flex items-center gap-3 font-mono text-xxs text-slate-400">
          <span>CPU {row.cpu_percent?.toFixed(0) ?? '—'}%</span>
          <span>RAM {row.memory_percent?.toFixed(0) ?? '—'}%</span>
          <span>Disk {row.disk_percent?.toFixed(0) ?? '—'}%</span>
        </div>
      ),
    },
    {
      key: 'network',
      header: 'Network',
      render: (row) => (
        <div className="flex items-center gap-3 font-mono text-xxs text-slate-400">
          <span>↓ {formatBitrate(row.network_rx_bps ?? 0)}</span>
          <span>↑ {formatBitrate(row.network_tx_bps ?? 0)}</span>
        </div>
      ),
    },
    { key: 'uptime', header: 'Uptime', render: (row) => formatDuration(row.uptime_seconds ?? 0) },
    { key: 'status', header: 'Status', render: (row) => <StatusBadge status={row.status} /> },
  ];

  return (
    <AppLayout>
      <PageHeader title="Servers" description="Backend servers and resource utilization" />

      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Local CPU" />
          <CardBody><MetricBar value={metrics?.cpu_percent ?? 0} /></CardBody>
        </Card>
        <Card>
          <CardHeader title="Local Memory" />
          <CardBody><MetricBar value={metrics?.memory_percent ?? 0} /></CardBody>
        </Card>
        <Card>
          <CardHeader title="Local Disk" />
          <CardBody><MetricBar value={metrics?.disk_percent ?? 0} /></CardBody>
        </Card>
      </div>

      <Card>
        <div className="border-b border-base-700 p-4">
          <Input
            type="search"
            placeholder="Search servers…"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <Table columns={columns} rows={data?.items ?? []} rowKey={(row) => row.id} empty="No servers registered." />
        <div className="flex items-center justify-between border-t border-base-700 px-4 py-3 text-xs text-muted">
          <span>{data?.total ?? 0} total</span>
          <div className="flex items-center gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              className="rounded-lg border border-base-600 px-3 py-1.5 disabled:opacity-50"
            >
              Previous
            </button>
            <span className="font-mono">{page}</span>
            <button
              disabled={(data?.pages ?? 1) <= page}
              onClick={() => setPage(page + 1)}
              className="rounded-lg border border-base-600 px-3 py-1.5 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      </Card>
    </AppLayout>
  );
}

function MetricBar({ value }: { value: number }) {
  const tone = value > 85 ? 'bg-red-500' : value > 65 ? 'bg-amber-500' : 'bg-accent-500';
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-xs">
        <span className="text-slate-400">Utilization</span>
        <span className="font-mono text-slate-300">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-base-700">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.min(100, value)}%` }} />
      </div>
    </div>
  );
}
