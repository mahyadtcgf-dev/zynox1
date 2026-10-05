import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { UserPlus, Trash2, Link2, Send } from 'lucide-react';
import { api } from '@/services/api';
import type { Paginated, TelegramStatus, TelegramUser, User } from '@/types';
import { AppLayout, PageHeader } from '@/layouts/AppLayout';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Table, type Column } from '@/components/ui/Table';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Field, Input, Select } from '@/components/ui/Field';
import { toast } from '@/stores/toast';
import { useAuthStore } from '@/stores/auth';
import { formatDateTime } from '@/utils/format';

export function TelegramPage() {
  const queryClient = useQueryClient();
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const [linkOpen, setLinkOpen] = useState(false);

  const { data: status } = useQuery<TelegramStatus>({
    queryKey: ['telegram-status'],
    queryFn: () => api.get<TelegramStatus>('/api/v1/telegram/status'),
  });

  const { data } = useQuery<Paginated<TelegramUser>>({
    queryKey: ['telegram-users'],
    queryFn: () => api.get<Paginated<TelegramUser>>('/api/v1/telegram/users', { page: 1, page_size: 100 }),
  });

  const unlinkMutation = useMutation({
    mutationFn: (telegramId: string) =>
      api.post('/api/v1/telegram/unlink', { telegram_id: telegramId }),
    onSuccess: () => {
      toast.success('Telegram user unlinked');
      queryClient.invalidateQueries({ queryKey: ['telegram-users'] });
    },
    onError: (error: unknown) => toast.error('Unlink failed', error instanceof Error ? error.message : undefined),
  });

  const columns: Column<TelegramUser>[] = [
    {
      key: 'user',
      header: 'Telegram user',
      render: (row) => (
        <div>
          <p className="font-medium text-slate-100">
            {row.first_name} {row.last_name}
          </p>
          <p className="font-mono text-xxs text-muted">
            @{row.username} · {row.telegram_id}
          </p>
        </div>
      ),
    },
    {
      key: 'linked',
      header: 'Panel account',
      render: (row) => (row.linked_username ? <Badge variant="info">{row.linked_username}</Badge> : <span className="text-muted">—</span>),
    },
    { key: 'linkedAt', header: 'Linked', render: (row) => formatDateTime(row.linked_at) },
    { key: 'seen', header: 'Last seen', render: (row) => formatDateTime(row.last_seen_at) },
    {
      key: 'status',
      header: 'Access',
      render: (row) => <StatusBadge status={row.is_authorized ? 'ok' : 'offline'} />,
    },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (row) =>
        hasPermission('telegram:update') ? (
          <button
            title="Unlink"
            onClick={() => {
              if (confirm(`Unlink Telegram account ${row.telegram_id}?`)) {
                unlinkMutation.mutate(row.telegram_id);
              }
            }}
            className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-red-500/10 hover:text-red-400"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        ) : null,
    },
  ];

  return (
    <AppLayout>
      <PageHeader
        title="Telegram"
        description="Management bot and Mini App access control"
        actions={
          hasPermission('telegram:update') ? (
            <Button variant="primary" onClick={() => setLinkOpen(true)}>
              <UserPlus className="h-4 w-4" />
              Link account
            </Button>
          ) : null
        }
      />

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader title="Bot status" />
          <CardBody>
            <div className="flex items-center gap-2">
              <Send className="h-4 w-4 text-slate-400" />
              <StatusBadge status={status?.bot_configured ? 'ok' : 'offline'} />
            </div>
            <p className="mt-2 text-xxs text-muted">
              {status?.bot_configured ? 'Token configured' : 'Set TELEGRAM_BOT_TOKEN to enable'}
            </p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Authorized users" />
          <CardBody>
            <p className="text-2xl font-semibold text-slate-100">{status?.authorized_users ?? 0}</p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Mini App" />
          <CardBody>
            <p className="truncate font-mono text-xs text-slate-300">
              {status?.mini_app_url ?? 'Not configured'}
            </p>
          </CardBody>
        </Card>
      </div>

      <Card>
        <Table
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(row) => row.id}
          empty="No Telegram accounts linked. A Telegram user is never an administrator by default."
        />
      </Card>

      {linkOpen ? <LinkModal onClose={() => setLinkOpen(false)} /> : null}
    </AppLayout>
  );
}

function LinkModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data: users } = useQuery<Paginated<User>>({
    queryKey: ['users-telegram-link'],
    queryFn: () => api.get<Paginated<User>>('/api/v1/users', { page: 1, page_size: 100 }),
  });
  const [telegramId, setTelegramId] = useState('');
  const [username, setUsername] = useState('');
  const [userId, setUserId] = useState('');

  const mutation = useMutation({
    mutationFn: () =>
      api.post('/api/v1/telegram/link', {
        telegram_id: telegramId,
        username: username || null,
        user_id: userId,
      }),
    onSuccess: () => {
      toast.success('Telegram account linked');
      queryClient.invalidateQueries({ queryKey: ['telegram-users'] });
      onClose();
    },
    onError: (error: unknown) => toast.error('Link failed', error instanceof Error ? error.message : undefined),
  });

  return (
    <Modal open onClose={onClose} title="Link Telegram account" size="md">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
        className="space-y-4"
      >
        <Field label="Telegram chat ID" hint="Numeric ID. Find it via the bot or @userinfobot.">
          <Input value={telegramId} onChange={(e) => setTelegramId(e.target.value)} placeholder="123456789" required />
        </Field>
        <Field label="Telegram username (optional)">
          <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
        </Field>
        <Field label="Panel account">
          <Select value={userId} onChange={(e) => setUserId(e.target.value)} required>
            <option value="">Select a user…</option>
            {(users?.items ?? []).map((user) => (
              <option key={user.id} value={user.id}>
                {user.username} ({user.roles.join(', ')})
              </option>
            ))}
          </Select>
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={mutation.isPending}>
            <Link2 className="h-4 w-4" />
            {mutation.isPending ? 'Linking…' : 'Link account'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
