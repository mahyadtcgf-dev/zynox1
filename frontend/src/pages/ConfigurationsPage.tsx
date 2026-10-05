import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Plus, Trash2, Copy, Download, Power, PowerOff } from 'lucide-react';
import { api } from '@/services/api';
import type { ConfigListItem, MessageOut, Paginated } from '@/types';
import { AppLayout, PageHeader } from '@/layouts/AppLayout';
import { Card } from '@/components/ui/Card';
import { Table, type Column } from '@/components/ui/Table';
import { StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Field';
import { ConfirmDialog } from '@/components/ui/Modal';
import { toast } from '@/stores/toast';
import { useAuthStore } from '@/stores/auth';
import { Pagination } from '@/components/shared/Pagination';
import { CopyButton } from '@/components/shared/CopyButton';
import { timeAgo } from '@/utils/format';
import { ConfigWizard } from '@/components/configs/ConfigWizard';

export function ConfigurationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const [page, setPage] = useState(Number(searchParams.get('page') ?? 1));
  const [search, setSearch] = useState(searchParams.get('search') ?? '');
  const [wizardOpen, setWizardOpen] = useState(false);
  const [toDelete, setToDelete] = useState<ConfigListItem | null>(null);

  const { data, isLoading } = useQuery<Paginated<ConfigListItem>>({
    queryKey: ['configs', page, search],
    queryFn: () =>
      api.get<Paginated<ConfigListItem>>('/api/v1/configurations', {
        page,
        page_size: 20,
        search: search || undefined,
      }),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ config, enable }: { config: ConfigListItem; enable: boolean }) =>
      api.post<MessageOut>(
        `/api/v1/configurations/${config.id}/${enable ? 'enable' : 'disable'}`,
        {}
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['configs'] });
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Operation failed';
      toast.error('Operation failed', message);
    },
  });

  const duplicateMutation = useMutation({
    mutationFn: (config: ConfigListItem) =>
      api.post<MessageOut>(`/api/v1/configurations/${config.id}/duplicate`, {}),
    onSuccess: () => {
      toast.success('Configuration duplicated');
      queryClient.invalidateQueries({ queryKey: ['configs'] });
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Duplicate failed';
      toast.error('Duplicate failed', message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete<MessageOut>(`/api/v1/configurations/${id}`),
    onSuccess: () => {
      toast.success('Configuration deleted');
      queryClient.invalidateQueries({ queryKey: ['configs'] });
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Delete failed';
      toast.error('Delete failed', message);
    },
  });

  const columns: Column<ConfigListItem>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (row) => (
        <div>
          <p className="font-medium text-slate-100">{row.name}</p>
          <p className="font-mono text-xxs text-muted">{row.uuid}</p>
        </div>
      ),
    },
    {
      key: 'protocol',
      header: 'Protocol',
      render: (row) => (
        <span className="rounded bg-base-700/60 px-1.5 py-0.5 font-mono text-xxs text-slate-300">
          {row.protocol} / {row.transport}
        </span>
      ),
    },
    { key: 'host', header: 'Host', render: (row) => <span className="font-mono text-xs">{row.host}</span> },
    {
      key: 'share',
      header: 'Share URL',
      render: (row) =>
        row.share_url ? <CopyButton value={row.share_url} label="Copy link" /> : <span className="text-muted">—</span>,
    },
    {
      key: 'expires',
      header: 'Expires',
      render: (row) => (row.expires_at ? <span className="text-muted">{timeAgo(row.expires_at)}</span> : 'Never'),
    },
    { key: 'enabled', header: 'Status', render: (row) => <StatusBadge status={row.enabled ? 'ok' : 'offline'} /> },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (row) => (
        <div className="flex items-center justify-end gap-1">
          {hasPermission('config:update') ? (
            <>
              {row.enabled ? (
                <button
                  title="Disable"
                  onClick={() => toggleMutation.mutate({ config: row, enable: false })}
                  className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-base-700 hover:text-slate-200"
                >
                  <PowerOff className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  title="Enable"
                  onClick={() => toggleMutation.mutate({ config: row, enable: true })}
                  className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-emerald-500/10 hover:text-emerald-400"
                >
                  <Power className="h-3.5 w-3.5" />
                </button>
              )}
            </>
          ) : null}
          {hasPermission('config:create') ? (
            <button
              title="Duplicate"
              onClick={() => duplicateMutation.mutate(row)}
              className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-base-700 hover:text-slate-200"
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
          ) : null}
          <a
            title="Export"
            href={`/api/v1/configurations/${row.id}/export`}
            className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-base-700 hover:text-slate-200"
          >
            <Download className="h-3.5 w-3.5" />
          </a>
          {hasPermission('config:delete') ? (
            <button
              title="Delete"
              onClick={() => setToDelete(row)}
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
        title="Configurations"
        description="Client configurations across TCP, WebSocket, and xHTTP"
        actions={
          hasPermission('config:create') ? (
            <Button variant="primary" onClick={() => setWizardOpen(true)}>
              <Plus className="h-4 w-4" />
              Generate configuration
            </Button>
          ) : null
        }
      />

      <Card>
        <div className="border-b border-base-700 p-4">
          <Input
            type="search"
            placeholder="Search configurations…"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
              setSearchParams({ search: event.target.value, page: '1' });
            }}
          />
        </div>
        <Table
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(row) => row.id}
          empty={isLoading ? 'Loading…' : 'No configurations yet. Generate one to get started.'}
        />
        <Pagination
          page={page}
          pages={data?.pages ?? 1}
          onPageChange={setPage}
        />
      </Card>

      {wizardOpen ? <ConfigWizard onClose={() => setWizardOpen(false)} /> : null}

      <ConfirmDialog
        open={toDelete !== null}
        onClose={() => setToDelete(null)}
        onConfirm={() => toDelete && deleteMutation.mutate(toDelete.id)}
        title="Delete configuration"
        description={`This will permanently delete "${toDelete?.name}" and revoke its client identity. This cannot be undone.`}
        confirmLabel="Delete configuration"
        destructive
      />
    </AppLayout>
  );
}
