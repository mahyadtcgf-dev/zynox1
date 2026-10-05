import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Copy, Check } from 'lucide-react';
import { useState } from 'react';
import { copyToClipboard } from '@/utils/format';
import { toast } from '@/stores/toast';

export function CopyButton({
  value,
  label = 'Copy',
  className,
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => copyToClipboard(value),
    onSuccess: () => {
      setCopied(true);
      toast.success('Copied to clipboard');
      setTimeout(() => setCopied(false), 1500);
      queryClient.invalidateQueries({ queryKey: ['configs'] });
    },
    onError: () => toast.error('Copy failed', 'Clipboard access was denied'),
  });

  return (
    <button
      type="button"
      onClick={() => mutation.mutate()}
      className={`inline-flex items-center gap-1.5 rounded-lg border border-base-600 bg-base-800 px-2.5 py-1.5 text-xs text-slate-200 transition-colors hover:bg-base-750 ${className ?? ''}`}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? 'Copied' : label}
    </button>
  );
}
