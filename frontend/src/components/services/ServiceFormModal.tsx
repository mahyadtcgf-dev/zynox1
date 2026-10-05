import { type FormEvent, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { Service } from '@/types';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { Field, Input, Select, TextArea } from '@/components/ui/Field';
import { toast } from '@/stores/toast';

const PROTOCOLS = ['vless', 'vmess', 'trojan'] as const;
const TRANSPORTS = ['tcp', 'ws', 'xhttp'] as const;

export function ServiceFormModal({
  service,
  onClose,
}: {
  service: Service | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(service?.name ?? '');
  const [description, setDescription] = useState(service?.description ?? '');
  const [host, setHost] = useState(service?.host ?? '');
  const [port, setPort] = useState(String(service?.port ?? 443));
  const [protocol, setProtocol] = useState<Service['protocol']>(service?.protocol ?? 'vless');
  const [transport, setTransport] = useState<Service['transport']>(service?.transport ?? 'tcp');
  const [tag, setTag] = useState(service?.tag ?? '');

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name,
        description: description || null,
        host,
        port: Number(port),
        protocol,
        transport,
        tag: tag || null,
      };
      if (service) {
        return api.patch<Service>(`/api/v1/services/${service.id}`, payload);
      }
      return api.post<Service>('/api/v1/services', payload);
    },
    onSuccess: () => {
      toast.success(service ? 'Service updated' : 'Service created');
      queryClient.invalidateQueries({ queryKey: ['services'] });
      onClose();
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Save failed';
      toast.error('Save failed', message);
    },
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={service ? 'Edit service' : 'New service'}
      description="Services represent a managed proxy instance."
      size="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Name">
          <Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="edge-01" />
        </Field>

        <Field label="Description">
          <TextArea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional notes about this service"
            rows={2}
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Host">
            <Input
              required
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="example.com"
            />
          </Field>
          <Field label="Port">
            <Input
              required
              type="number"
              min={1}
              max={65535}
              value={port}
              onChange={(e) => setPort(e.target.value)}
            />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Protocol">
            <Select value={protocol} onChange={(e) => setProtocol(e.target.value as Service['protocol'])}>
              {PROTOCOLS.map((value) => (
                <option key={value} value={value}>
                  {value.toUpperCase()}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Transport">
            <Select value={transport} onChange={(e) => setTransport(e.target.value as Service['transport'])}>
              {TRANSPORTS.map((value) => (
                <option key={value} value={value}>
                  {value === 'ws' ? 'WebSocket' : value === 'xhttp' ? 'xHTTP' : 'TCP'}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="Tag" hint="Inbound tag used by the Xray adapter. Optional.">
          <Input value={tag} onChange={(e) => setTag(e.target.value)} placeholder="inbound-edge-01" />
        </Field>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : service ? 'Save changes' : 'Create service'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
