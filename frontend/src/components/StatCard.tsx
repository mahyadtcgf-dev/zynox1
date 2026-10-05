import { type ReactNode } from 'react';
import { Card } from '@/components/ui/Card';

export function StatCard({
  label,
  value,
  icon: Icon,
  tone = 'neutral',
  hint,
}: {
  label: string;
  value: ReactNode;
  icon: React.ComponentType<{ className?: string }>;
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
  hint?: string;
}) {
  const toneClasses = {
    neutral: 'text-slate-400',
    success: 'text-emerald-400',
    warning: 'text-amber-400',
    danger: 'text-red-400',
  };

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <p className="text-xxs font-medium uppercase tracking-wide text-muted">{label}</p>
        <Icon className={`h-4 w-4 ${toneClasses[tone]}`} />
      </div>
      <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-100">{value}</p>
      {hint ? <p className="mt-1 text-xxs text-muted">{hint}</p> : null}
    </Card>
  );
}
