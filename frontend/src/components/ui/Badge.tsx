import { clsx } from 'clsx';

type Variant = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

const styles: Record<Variant, string> = {
  neutral: 'bg-base-700/60 text-slate-300 ring-base-600',
  success: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/30',
  warning: 'bg-amber-500/10 text-amber-400 ring-amber-500/30',
  danger: 'bg-red-500/10 text-red-400 ring-red-500/30',
  info: 'bg-blue-500/10 text-blue-400 ring-blue-500/30',
};

export function Badge({
  children,
  variant = 'neutral',
  className,
}: {
  children: React.ReactNode;
  variant?: Variant;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xxs font-medium uppercase tracking-wide ring-1 ring-inset',
        styles[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const variant: Variant =
    status === 'running' || status === 'online' || status === 'ok'
      ? 'success'
      : status === 'stopped' || status === 'offline' || status === 'error'
        ? 'danger'
        : status === 'degraded' || status === 'warning'
          ? 'warning'
          : 'neutral';

  const label =
    status === 'unknown'
      ? 'Unknown'
      : status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <Badge variant={variant}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </Badge>
  );
}
