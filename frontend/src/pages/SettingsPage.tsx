import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Save } from 'lucide-react';
import { api } from '@/services/api';
import type { SystemSetting, User } from '@/types';
import { AppLayout, PageHeader } from '@/layouts/AppLayout';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { toast } from '@/stores/toast';
import { useAuthStore } from '@/stores/auth';
import { useState } from 'react';

const EDITABLE = [
  { key: 'app.name', label: 'Application name', placeholder: 'Zynox' },
  { key: 'app.motd', label: 'Dashboard message', placeholder: 'Welcome' },
  { key: 'telegram.mini_app_url', label: 'Telegram Mini App URL', placeholder: 'https://example.com/mini-app' },
  { key: 'xray.control_mode', label: 'Xray control mode', placeholder: 'local | api | disabled' },
  { key: 'xray.binary_path', label: 'Xray binary path', placeholder: '/usr/local/bin/xray' },
  { key: 'xray.config_path', label: 'Xray config path', placeholder: '/etc/xray/config.json' },
];

export function SettingsPage() {
  const { data: user } = useQuery<User>({ queryKey: ['me'], queryFn: () => api.get<User>('/api/v1/auth/me') });
  const canEdit = useAuthStore((s) => s.hasPermission)('setting:update');

  return (
    <AppLayout>
      <PageHeader title="Settings" description="System configuration" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Account" description="Your panel identity" />
          <CardBody>
            <div className="space-y-3 text-sm">
              <Row label="Username" value={user?.username} />
              <Row label="Email" value={user?.email} />
              <Row label="Roles" value={user?.roles.join(', ')} />
              <Row label="Two-factor" value={user?.totp_enabled ? 'Enabled' : 'Disabled'} />
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="System settings" description="Stored in the database" />
          <CardBody>
            <SettingsForm disabled={!canEdit} />
          </CardBody>
        </Card>
      </div>
    </AppLayout>
  );
}

function Row({ label, value }: { label: string; value?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-base-800 pb-2">
      <span className="text-muted">{label}</span>
      <span className="text-slate-200">{value ?? '—'}</span>
    </div>
  );
}

function SettingsForm({ disabled }: { disabled: boolean }) {
  const queryClient = useQueryClient();
  const { data } = useQuery<SystemSetting[]>({
    queryKey: ['settings'],
    queryFn: () => api.get<SystemSetting[]>('/api/v1/settings'),
  });
  const [values, setValues] = useState<Record<string, string>>({});

  const upsert = useMutation({
    mutationFn: (payload: { key: string; value: string | null }) =>
      api.put<SystemSetting>('/api/v1/settings', payload),
    onSuccess: () => {
      toast.success('Setting saved');
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
    onError: (error: unknown) => toast.error('Save failed', error instanceof Error ? error.message : undefined),
  });

  return (
    <div className="space-y-4">
      {EDITABLE.map((field) => {
        const current = data?.find((setting) => setting.key === field.key)?.value ?? '';
        const value = values[field.key] ?? current;
        return (
          <Field key={field.key} label={field.label}>
            <div className="flex gap-2">
              <Input
                disabled={disabled}
                value={value}
                placeholder={field.placeholder}
                onChange={(event) => setValues({ ...values, [field.key]: event.target.value })}
              />
              <Button
                type="button"
                disabled={disabled || value === current}
                onClick={() => upsert.mutate({ key: field.key, value: value || null })}
              >
                <Save className="h-3.5 w-3.5" />
              </Button>
            </div>
          </Field>
        );
      })}
      {disabled ? <p className="text-xxs text-muted">You need the setting:update permission to edit these.</p> : null}
    </div>
  );
}
