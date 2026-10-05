import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Plus, RotateCw, Play, Square, Trash2, Pencil, Zap } from 'lucide-react';
import { api } from '@/services/api';
import type { MessageOut, Paginated, Service } from '@/types';
import { AppLayout, PageHeader } from '@/layouts/AppLayout';
import { Card } from '@/components/ui/Card';
import { Table, type Column } from '@/components/ui/Table';
import { StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Field';
import { toast } from '@/stores/toast';
import { Pagination } from '@/components/shared/Pagination';
import { useAuthStore } from '@/stores/auth';

import { ServiceFormModal } from '@/components/services/ServiceFormModal';

export function ServicesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const [page, setPage] = useState(Number(searchParams.get('page') ?? 1));
  const [search, setSearch] = useState(searchParams.get('search') ?? '');
  const [toDelete, setToDelete] = useState<Service | null>(null);
  const [editing, setEditing] = useState<Service | null>(null);
  const [creating, setCreating] = useState(false);

  const { data, isLoading } = useQuery<Paginated<Service>>({
    queryKey: ['services', page, search],
    queryFn: () =>
      api.get<Paginated<Service>>('/api/v1/services', {
        page,
        page_size: 20,
        search: search || undefined,
      }),
  });

  const actionMutation = useMutation({
    mutationFn: ({ service, action }: { service: Service; action: string }) =>
      api.post<{ action: string; status: string; message: string }>(
        `/api/v1/services/${service.id}/action`,
        { action }
      ),
    onSuccess: (result, variables) => {
      toast.success(`${variables.service.name}: ${result.message}`);
      queryClient.invalidateQueries({ queryKey: ['services'] });
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Action failed';
      toast.error('Action failed', message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete<MessageOut>(`/api/v1/services/${id}`),
    onSuccess: () => {
      toast.success('Service deleted');
      queryClient.invalidateQueries({ queryKey: ['services'] });
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Delete failed';
      toast.error('Delete failed', message);
    },
  });

  const columns: Column<Service>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (row) => (
        <div>
          <p className="font-medium text-slate-100">{row.name}</p>
          {row.description ? <p className="text-xxs text-muted">{row.description}</p> : null}
        </div>
      ),
    },
    { key: 'host', header: 'Host', render: (row) => <span className="font-mono text-xs">{row.host}:{row.port}</span> },
    {
      key: 'protocol',
      header: 'Protocol',
      render: (row) => (
        <span className="rounded bg-base-700/60 px-1.5 py-0.5 font-mono text-xxs text-slate-300">
          {row.protocol} / {row.transport}
        </span>
      ),
    },
    { key: 'configs', header: 'Configs', render: (row) => row.config_count },
    { key: 'status', header: 'Status', render: (row) => <StatusBadge status={row.enabled ? row.status : 'disabled'} /> },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (row) => (
        <div className="flex items-center justify-end gap-1">
          {hasPermission('service:control') ? (
            <>
              <IconAction
                title="Start"
                onClick={() => actionMutation.mutate({ service: row, action: 'start' })}
              >
                <Play className="h-3.5 w-3.5" />
              </IconAction>
              <IconAction
                title="Stop"
                onClick={() => actionMutation.mutate({ service: row, action: 'stop' })}
              >
                <Square className="h-3.5 w-3.5" />
              </IconAction>
              <IconAction
                title="Restart"
                onClick={() => actionMutation.mutate({ service: row, action: 'restart' })}
              >
                <RotateCw className="h-3.5 w-3.5" />
              </IconAction>
              <IconAction
                title="Test connectivity"
                onClick={() => actionMutation.mutate({ service: row, action: 'test' })}
              >
                <Zap className="h-3.5 w-3.5" />
              </IconAction>
            </>
          ) : null}
          {hasPermission('service:update') ? (
            <IconAction title="Edit" onClick={() => setEditing(row)}>
              <Pencil className="h-3.5 w-3.5" />
            </IconAction>
          ) : null}
          {hasPermission('service:delete') ? (
            <IconAction title="Delete" destructive onClick={() => setToDelete(row)}>
              <Trash2 className="h-3.5 w-3.5" />
            </IconAction>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <AppLayout>
      <PageHeader
        title="Services"
        description="Managed proxy service instances"
        actions={
          hasPermission('service:create') ? (
            <Button variant="primary" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" />
              New service
            </Button>
          ) : null
        }
      />

      <Card>
        <div className="border-b border-base-700 p-4">
          <Input
            type="search"
            placeholder="Search services…"
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
          empty={isLoading ? 'Loading…' : 'No services yet. Create one to get started.'}
        />
        <Pagination
          page={page}
          pages={data?.pages ?? 1}
          onPageChange={setPage}
        />
      </Card>

      {creating || editing ? (
        <ServiceFormModal
          service={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      ) : null}

      <ConfirmDialog
        open={toDelete !== null}
        onClose={() => setToDelete(null)}
        onConfirm={() => toDelete && deleteMutation.mutate(toDelete.id)}
        title="Delete service"
        description={`This will delete "${toDelete?.name}". Configurations bound to it will be unlinked, not deleted. This cannot be undone.`}
        confirmLabel="Delete service"
        destructive
      />
    </AppLayout>
  );
}

function IconAction({
  children,
  title,
  onClick,
  destructive,
}: {
  children: React.ReactNode;
  title: string;
  onClick: () => void;
  destructive?: boolean;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={`rounded-md p-1.5 transition-colors ${
        destructive
          ? 'text-slate-500 hover:bg-red-500/10 hover:text-red-400'
          : 'text-slate-500 hover:bg-base-700 hover:text-slate-200'
      }`}
    >
      {children}
    </button>
  );
}
