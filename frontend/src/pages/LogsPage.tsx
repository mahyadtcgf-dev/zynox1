import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { AuditLog, Paginated } from '@/types';
import { AppLayout, PageHeader } from '@/layouts/AppLayout';
import { Card } from '@/components/ui/Card';
import { Table, type Column } from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import { Input, Select } from '@/components/ui/Field';
import { formatDateTime } from '@/utils/format';

export function LogsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [resourceType, setResourceType] = useState('');

  const { data } = useQuery<Paginated<AuditLog>>({
    queryKey: ['audit-logs', page, search, resourceType],
    queryFn: () =>
      api.get<Paginated<AuditLog>>('/api/v1/logs/audit', {
        page,
        page_size: 25,
        search: search || undefined,
        resource_type: resourceType || undefined,
      }),
  });

  const columns: Column<AuditLog>[] = [
    { key: 'time', header: 'Time', render: (row) => <span className="text-muted">{formatDateTime(row.created_at)}</span> },
    {
      key: 'action',
      header: 'Action',
      render: (row) => <span className="font-mono text-xs text-slate-200">{row.action}</span>,
    },
    { key: 'actor', header: 'Actor', render: (row) => row.actor_username ?? '—' },
    {
      key: 'resource',
      header: 'Resource',
      render: (row) => (
        <span className="font-mono text-xxs text-muted">
          {row.resource_type}
          {row.resource_id ? ` · ${row.resource_id.slice(0, 8)}` : ''}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <Badge variant={row.status === 'success' ? 'success' : 'danger'}>{row.status}</Badge>
      ),
    },
    { key: 'ip', header: 'IP', render: (row) => <span className="font-mono text-xxs text-muted">{row.ip_address ?? '—'}</span> },
  ];

  return (
    <AppLayout>
      <PageHeader title="Audit Logs" description="Immutable record of privileged actions" />

      <Card>
        <div className="flex flex-col gap-3 border-b border-base-700 p-4 sm:flex-row">
          <Input
            type="search"
            placeholder="Search by action…"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
            className="flex-1"
          />
          <Select
            value={resourceType}
            onChange={(event) => {
              setResourceType(event.target.value);
              setPage(1);
            }}
            className="sm:w-48"
          >
            <option value="">All resources</option>
            <option value="service">Services</option>
            <option value="config">Configurations</option>
            <option value="user">Users</option>
            <option value="telegram_user">Telegram</option>
          </Select>
        </div>
        <Table columns={columns} rows={data?.items ?? []} rowKey={(row) => row.id} empty="No activity recorded." />
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
