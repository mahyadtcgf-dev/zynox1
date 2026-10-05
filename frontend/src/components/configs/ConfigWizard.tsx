import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Check, ChevronRight, ChevronLeft, Download } from 'lucide-react';
import { api } from '@/services/api';
import type { ConfigGenerated, Paginated, Service } from '@/types';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { Field, Input, Select } from '@/components/ui/Field';
import { toast } from '@/stores/toast';
import { CopyButton } from '@/components/shared/CopyButton';
import { clsx } from 'clsx';

const PROTOCOLS = ['vless', 'vmess', 'trojan'] as const;
const TRANSPORTS = ['tcp', 'ws', 'xhttp'] as const;
const SECURITIES = ['none', 'tls', 'reality', 'xtls'] as const;
const FINGERPRINTS = ['chrome', 'firefox', 'safari', 'ios', 'android', 'edge', 'random'];
const XHTTP_MODES = ['packet-up', 'stream-up', 'stream-one'];

const STEPS = ['Server', 'Protocol', 'Transport', 'Transport settings', 'Security', 'Review', 'Generate'] as const;

interface FormState {
  serviceId: string;
  name: string;
  protocol: (typeof PROTOCOLS)[number];
  transport: (typeof TRANSPORTS)[number];
  host: string;
  port: string;
  path: string;
  hostHeader: string;
  sni: string;
  flow: string;
  security: (typeof SECURITIES)[number];
  fingerprint: string;
  alpn: string;
  allowInsecure: boolean;
  xhttpMode: string;
}

function initialForm(host = ''): FormState {
  return {
    serviceId: '',
    name: '',
    protocol: 'vless',
    transport: 'tcp',
    host,
    port: '443',
    path: '/',
    hostHeader: '',
    sni: '',
    flow: '',
    security: 'tls',
    fingerprint: 'chrome',
    alpn: '',
    allowInsecure: false,
    xhttpMode: 'packet-up',
  };
}

export function ConfigWizard({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [result, setResult] = useState<ConfigGenerated | null>(null);
  const [form, setForm] = useState<FormState>(initialForm());

  const { data: services } = useQuery<Paginated<Service>>({
    queryKey: ['services-wizard'],
    queryFn: () => api.get<Paginated<Service>>('/api/v1/services', { page: 1, page_size: 100 }),
  });

  const generate = useMutation({
    mutationFn: () =>
      api.post<ConfigGenerated>('/api/v1/configurations/generate', {
        config: {
          name: form.name,
          protocol: form.protocol,
          transport: form.transport,
          host: form.host,
          port: Number(form.port),
          service_id: form.serviceId || null,
          path: form.transport === 'tcp' ? null : form.path,
          host_header: form.hostHeader || null,
          sni: form.sni || null,
          flow: form.transport === 'tcp' ? form.flow || null : null,
          security: form.security,
          fingerprint: form.fingerprint || null,
          alpn: form.alpn || null,
          allow_insecure: form.allowInsecure,
          extra: form.transport === 'xhttp' ? { mode: form.xhttpMode } : null,
        },
      }),
    onSuccess: (data) => {
      setResult(data);
      toast.success('Configuration generated');
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Generation failed';
      toast.error('Generation failed', message);
    },
  });

  const update = (patch: Partial<FormState>) => setForm((prev) => ({ ...prev, ...patch }));

  const selectService = (serviceId: string) => {
    const service = services?.items.find((item) => item.id === serviceId);
    update({
      serviceId,
      host: service?.host ?? form.host,
      port: service ? String(service.port) : form.port,
      protocol: (service?.protocol ?? form.protocol) as FormState['protocol'],
      transport: (service?.transport ?? form.transport) as FormState['transport'],
      name: form.name || service?.name ? `${service?.name}-client` : '',
    });
  };

  const canContinue = (): boolean => {
    switch (step) {
      case 0:
        return true;
      case 1:
        return form.name.trim().length > 0;
      case 2:
        return true;
      case 3:
        return form.host.trim().length > 0 && Number(form.port) > 0;
      case 4:
        return form.security === 'none' || form.sni.trim().length > 0;
      default:
        return true;
    }
  };

  const next = () => setStep((current) => Math.min(STEPS.length - 1, current + 1));
  const previous = () => setStep((current) => Math.max(0, current - 1));

  return (
    <Modal
      open
      onClose={onClose}
      size="xl"
      title="Generate configuration"
      description="Create a validated client configuration in a few steps."
    >
      {result ? (
        <GeneratedView result={result} onClose={onClose} />
      ) : (
        <div>
          <Stepper current={step} />

          <div className="mt-6 min-h-[16rem]">
            {step === 0 ? (
              <Field label="Service" hint="Optional — pre-fills host, port, protocol and transport.">
                <Select value={form.serviceId} onChange={(event) => selectService(event.target.value)}>
                  <option value="">None — configure manually</option>
                  {(services?.items ?? []).map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.name} ({service.host}:{service.port})
                    </option>
                  ))}
                </Select>
              </Field>
            ) : null}

            {step === 1 ? (
              <div className="space-y-4">
                <Field label="Configuration name">
                  <Input
                    value={form.name}
                    onChange={(event) => update({ name: event.target.value })}
                    placeholder="client-01"
                  />
                </Field>
                <Field label="Protocol">
                  <Select value={form.protocol} onChange={(event) => update({ protocol: event.target.value as FormState['protocol'] })}>
                    {PROTOCOLS.map((value) => (
                      <option key={value} value={value}>
                        {value.toUpperCase()}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
            ) : null}

            {step === 2 ? (
              <Field label="Transport">
                <Select value={form.transport} onChange={(event) => update({ transport: event.target.value as FormState['transport'] })}>
                  {TRANSPORTS.map((value) => (
                    <option key={value} value={value}>
                      {value === 'ws' ? 'WebSocket' : value === 'xhttp' ? 'xHTTP' : 'TCP'}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : null}

            {step === 3 ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Host">
                    <Input value={form.host} onChange={(event) => update({ host: event.target.value })} placeholder="example.com" />
                  </Field>
                  <Field label="Port">
                    <Input
                      type="number"
                      min={1}
                      max={65535}
                      value={form.port}
                      onChange={(event) => update({ port: event.target.value })}
                    />
                  </Field>
                </div>

                {form.transport === 'tcp' ? (
                  <Field label="Flow" hint="Only used by VLESS over TCP with TLS/XTLS.">
                    <Select value={form.flow} onChange={(event) => update({ flow: event.target.value })}>
                      <option value="">None</option>
                      <option value="xtls-rprx-vision">xtls-rprx-vision</option>
                      <option value="xtls-rprx-direct">xtls-rprx-direct</option>
                      <option value="xtls-rprx-origin">xtls-rprx-origin</option>
                    </Select>
                  </Field>
                ) : null}

                {form.transport === 'ws' ? (
                  <div className="space-y-4">
                    <Field label="Path">
                      <Input value={form.path} onChange={(event) => update({ path: event.target.value })} placeholder="/" />
                    </Field>
                    <Field label="Host header" hint="Optional WebSocket Host header.">
                      <Input
                        value={form.hostHeader}
                        onChange={(event) => update({ hostHeader: event.target.value })}
                        placeholder="example.com"
                      />
                    </Field>
                  </div>
                ) : null}

                {form.transport === 'xhttp' ? (
                  <div className="space-y-4">
                    <Field label="Mode">
                      <Select value={form.xhttpMode} onChange={(event) => update({ xhttpMode: event.target.value })}>
                        {XHTTP_MODES.map((mode) => (
                          <option key={mode} value={mode}>
                            {mode}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Path">
                      <Input value={form.path} onChange={(event) => update({ path: event.target.value })} placeholder="/" />
                    </Field>
                    <Field label="Host header">
                      <Input
                        value={form.hostHeader}
                        onChange={(event) => update({ hostHeader: event.target.value })}
                        placeholder="example.com"
                      />
                    </Field>
                  </div>
                ) : null}
              </div>
            ) : null}

            {step === 4 ? (
              <div className="space-y-4">
                <Field label="Security">
                  <Select value={form.security} onChange={(event) => update({ security: event.target.value as FormState['security'] })}>
                    {SECURITIES.map((value) => (
                      <option key={value} value={value}>
                        {value === 'none' ? 'None' : value.toUpperCase()}
                      </option>
                    ))}
                  </Select>
                </Field>
                {form.security !== 'none' ? (
                  <>
                    <Field label="SNI / Server name">
                      <Input
                        value={form.sni}
                        onChange={(event) => update({ sni: event.target.value })}
                        placeholder={form.host}
                      />
                    </Field>
                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Fingerprint">
                        <Select value={form.fingerprint} onChange={(event) => update({ fingerprint: event.target.value })}>
                          {FINGERPRINTS.map((value) => (
                            <option key={value} value={value}>
                              {value}
                            </option>
                          ))}
                        </Select>
                      </Field>
                      <Field label="ALPN" hint="Comma-separated, e.g. h2,http/1.1">
                        <Input value={form.alpn} onChange={(event) => update({ alpn: event.target.value })} />
                      </Field>
                    </div>
                    <label className="flex items-center gap-2.5 text-sm text-slate-300">
                      <input
                        type="checkbox"
                        checked={form.allowInsecure}
                        onChange={(event) => update({ allowInsecure: event.target.checked })}
                        className="h-4 w-4 rounded border-base-600 bg-base-900 text-accent-500 focus:ring-accent-500"
                      />
                      Allow insecure TLS
                    </label>
                  </>
                ) : null}
              </div>
            ) : null}

            {step === 5 ? (
              <div className="space-y-3">
                <SummaryRow label="Name" value={form.name} />
                <SummaryRow label="Protocol" value={form.protocol.toUpperCase()} />
                <SummaryRow
                  label="Transport"
                  value={form.transport === 'ws' ? 'WebSocket' : form.transport === 'xhttp' ? 'xHTTP' : 'TCP'}
                />
                <SummaryRow label="Host" value={`${form.host}:${form.port}`} />
                {form.transport !== 'tcp' ? <SummaryRow label="Path" value={form.path} /> : null}
                {form.transport === 'xhttp' ? <SummaryRow label="Mode" value={form.xhttpMode} /> : null}
                {form.flow ? <SummaryRow label="Flow" value={form.flow} /> : null}
                <SummaryRow label="Security" value={form.security.toUpperCase()} />
                {form.security !== 'none' ? (
                  <>
                    <SummaryRow label="SNI" value={form.sni || form.host} />
                    <SummaryRow label="Fingerprint" value={form.fingerprint} />
                  </>
                ) : null}
              </div>
            ) : null}

            {step === 6 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <p className="text-sm text-slate-300">Everything is configured.</p>
                <p className="mt-1 text-xs text-muted">
                  A unique client identity will be generated and the configuration validated.
                </p>
                <Button
                  variant="primary"
                  size="lg"
                  className="mt-6"
                  disabled={generate.isPending}
                  onClick={() => generate.mutate()}
                >
                  {generate.isPending ? 'Generating…' : 'Generate configuration'}
                </Button>
              </div>
            ) : null}
          </div>

          {step < 6 ? (
            <div className="mt-6 flex items-center justify-between border-t border-base-700 pt-4">
              <Button onClick={previous} disabled={step === 0}>
                <ChevronLeft className="h-4 w-4" />
                Back
              </Button>
              <Button variant="primary" onClick={next} disabled={!canContinue()}>
                Continue
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </Modal>
  );
}

function Stepper({ current }: { current: number }) {
  return (
    <ol className="flex items-center gap-1 overflow-x-auto">
      {STEPS.map((label, index) => (
        <li key={label} className="flex flex-shrink-0 items-center gap-1">
          <span
            className={clsx(
              'flex h-6 w-6 items-center justify-center rounded-full text-xxs font-medium',
              index < current
                ? 'bg-emerald-500/15 text-emerald-400'
                : index === current
                  ? 'bg-accent-600 text-white'
                  : 'bg-base-700 text-slate-500'
            )}
          >
            {index < current ? <Check className="h-3 w-3" /> : index + 1}
          </span>
          <span
            className={clsx(
              'hidden text-xxs sm:block',
              index <= current ? 'text-slate-300' : 'text-slate-600'
            )}
          >
            {label}
          </span>
          {index < STEPS.length - 1 ? (
            <ChevronRight className="mx-1 h-3.5 w-3.5 flex-shrink-0 text-slate-600" />
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-base-800 pb-2 text-sm">
      <span className="text-muted">{label}</span>
      <span className="font-mono text-slate-200">{value}</span>
    </div>
  );
}

function GeneratedView({
  result,
  onClose,
}: {
  result: ConfigGenerated;
  onClose: () => void;
}) {
  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-400">
        Configuration generated successfully.
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-slate-400">Client identity</p>
        <div className="flex items-center gap-2 rounded-lg border border-base-700 bg-base-900 px-3 py-2">
          <code className="flex-1 overflow-x-auto font-mono text-xs text-slate-300">
            {result.config.uuid}
          </code>
          <CopyButton value={result.config.uuid} />
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-slate-400">Share URL</p>
        <div className="flex items-center gap-2 rounded-lg border border-base-700 bg-base-900 px-3 py-2">
          <code className="flex-1 overflow-x-auto font-mono text-xs text-slate-300">
            {result.share_url}
          </code>
          <CopyButton value={result.share_url} />
        </div>
      </div>

      {result.qr_code ? (
        <div>
          <p className="mb-1.5 text-xs font-medium text-slate-400">QR code</p>
          <div className="rounded-lg border border-base-700 bg-white p-3">
            <img src={result.qr_code} alt="Configuration QR code" className="h-40 w-40" />
          </div>
        </div>
      ) : null}

      <div>
        <p className="mb-1.5 text-xs font-medium text-slate-400">Xray stream settings</p>
        <pre className="max-h-48 overflow-auto rounded-lg border border-base-700 bg-base-900 p-3 font-mono text-xxs text-slate-300">
          {JSON.stringify(result.xray, null, 2)}
        </pre>
      </div>

      <div className="flex justify-end gap-2 border-t border-base-700 pt-4">
        <a href={`/api/v1/configurations/${result.config.id}/export`}>
          <Button>
            <Download className="h-4 w-4" />
            Export
          </Button>
        </a>
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      </div>
    </div>
  );
}
