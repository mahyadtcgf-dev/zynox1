import { useQuery } from '@tanstack/react-query';
import {
  Server as ServerIcon,
  FileCog,
  Users,
  HardDrive,
  Cpu,
  MemoryStick,
  HardDrive as DiskIcon,
  Activity,
  Send,
} from 'lucide-react';
import { api } from '@/services/api';
import type { DashboardStats } from '@/types';
import { AppLayout, PageHeader } from '@/layouts/AppLayout';
import { StatCard } from '@/components/StatCard';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/Badge';
import { Table } from '@/components/ui/Table';
import { formatBitrate, formatDuration, timeAgo } from '@/utils/format';

export function DashboardPage() {
  const { data, isLoading, isError, refetch } = useQuery<DashboardStats>({
    queryKey: ['dashboard-stats'],
    queryFn: () => api.get<DashboardStats>('/api/v1/dashboard/stats'),
    refetchInterval: 30_000,
  });

  if (isError) {
    return (
      <AppLayout>
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <p className="text-sm text-slate-400">Failed to load dashboard data.</p>
          <button
            onClick={() => refetch()}
            className="mt-3 rounded-lg border border-base-600 bg-base-800 px-4 py-2 text-sm text-slate-200 hover:bg-base-750"
          >
            Retry
          </button>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <PageHeader
        title="Dashboard"
        description={data ? `System status for ${data.app_name}` : 'System status'}
      />

      {isLoading || !data ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div
              key={index}
              className="h-28 animate-pulse rounded-xl border border-base-700 bg-base-850/60"
            />
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Services"
              value={data.services_total}
              icon={ServerIcon}
              tone={data.services_offline > 0 ? 'warning' : 'success'}
              hint={`${data.services_active} active · ${data.services_offline} offline`}
            />
            <StatCard
              label="Configurations"
              value={data.configs_total}
              icon={FileCog}
              tone={data.configs_expired > 0 ? 'warning' : 'neutral'}
              hint={`${data.configs_active} active · ${data.configs_expired} expired`}
            />
            <StatCard
              label="Users"
              value={data.users_total}
              icon={Users}
              hint={`${data.users_active} active`}
            />
            <StatCard
              label="Servers"
              value={data.servers_total}
              icon={HardDrive}
              tone={data.servers_online === data.servers_total ? 'success' : 'warning'}
              hint={`${data.servers_online} online`}
            />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader title="System Resources" description="Local host metrics" />
              <CardBody>
                {data.system ? (
                  <div className="space-y-5">
                    <ResourceBar label="CPU" value={data.system.cpu_percent} icon={Cpu} />
                    <ResourceBar label="Memory" value={data.system.memory_percent} icon={MemoryStick} />
                    <ResourceBar label="Disk" value={data.system.disk_percent} icon={DiskIcon} />
                    <div className="grid grid-cols-2 gap-4 border-t border-base-700 pt-4 sm:grid-cols-3">
                      <Metric
                        label="Network in"
                        value={formatBitrate(data.system.network_rx_bps)}
                        icon={Activity}
                      />
                      <Metric
                        label="Network out"
                        value={formatBitrate(data.system.network_tx_bps)}
                        icon={Activity}
                      />
                      <Metric
                        label="Uptime"
                        value={formatDuration(data.system.uptime_seconds)}
                        icon={HardDrive}
                      />
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted">Metrics unavailable.</p>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Integrations" />
              <CardBody>
                <div className="space-y-3">
                  <IntegrationRow
                    name="Telegram bot"
                    status={data.telegram_bot_configured ? 'ok' : 'offline'}
                    detail={
                      data.telegram_bot_configured
                        ? `${data.telegram_authorized_users} authorized`
                        : 'Not configured'
                    }
                    icon={Send}
                  />
                </div>
              </CardBody>
            </Card>
          </div>

          <div className="mt-6">
            <Card>
              <CardHeader title="Recent Activity" description="Latest administrative actions" />
              <Table
                columns={[
                  {
                    key: 'action',
                    header: 'Action',
                    render: (row) => <span className="font-mono text-xs">{row.action}</span>,
                  },
                  { key: 'actor', header: 'Actor', render: (row) => row.actor_username ?? '—' },
                  {
                    key: 'resource',
                    header: 'Resource',
                    render: (row) => `${row.resource_type}${row.resource_id ? ` · ${row.resource_id.slice(0, 8)}` : ''}`,
                  },
                  {
                    key: 'status',
                    header: 'Status',
                    render: (row) => <StatusBadge status={row.status === 'success' ? 'ok' : 'error'} />,
                  },
                  {
                    key: 'when',
                    header: 'When',
                    render: (row) => <span className="text-muted">{timeAgo(row.created_at)}</span>,
                  },
                ]}
                rows={data.recent_activity}
                rowKey={(row) => row.id}
                empty="No activity recorded yet."
              />
            </Card>
          </div>
        </>
      )}
    </AppLayout>
  );
}

function ResourceBar({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
}) {
  const tone = value > 85 ? 'bg-red-500' : value > 65 ? 'bg-amber-500' : 'bg-accent-500';
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-slate-400">
          <Icon className="h-3.5 w-3.5" />
          {label}
        </span>
        <span className="font-mono text-slate-300">{value.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-base-700">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.min(100, value)}%` }} />
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-xxs text-muted">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </p>
      <p className="mt-1 font-mono text-sm text-slate-200">{value}</p>
    </div>
  );
}

function IntegrationRow({
  name,
  status,
  detail,
  icon: Icon,
}: {
  name: string;
  status: 'ok' | 'offline';
  detail: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-base-700 bg-base-900/40 px-3 py-2.5">
      <div className="flex items-center gap-2.5">
        <Icon className="h-4 w-4 text-slate-400" />
        <div>
          <p className="text-sm text-slate-200">{name}</p>
          <p className="text-xxs text-muted">{detail}</p>
        </div>
      </div>
      <StatusBadge status={status} />
    </div>
  );
}
