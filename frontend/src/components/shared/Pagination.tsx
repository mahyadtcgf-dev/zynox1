import { clsx } from 'clsx';

interface PaginationProps {
  page: number;
  pages: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, pages, onPageChange }: PaginationProps) {
  if (pages <= 1) return null;

  const windowSize = 5;
  const start = Math.max(1, page - Math.floor(windowSize / 2));
  const end = Math.min(pages, start + windowSize - 1);
  const visible: number[] = [];
  for (let i = start; i <= end; i += 1) visible.push(i);

  return (
    <div className="flex items-center justify-between gap-4 border-t border-base-800 px-4 py-3">
      <p className="text-xxs text-muted">
        Page {page} of {pages}
      </p>
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={page === 1}
          onClick={() => onPageChange(page - 1)}
          className="rounded-md border border-base-700 px-2.5 py-1 text-xs text-slate-300 transition-colors hover:bg-base-800 disabled:opacity-40"
        >
          Prev
        </button>
        {visible.map((item) => (
          <button
            type="button"
            key={item}
            onClick={() => onPageChange(item)}
            className={clsx(
              'rounded-md border px-2.5 py-1 text-xs transition-colors',
              item === page
                ? 'border-accent-600 bg-accent-600/15 text-accent-400'
                : 'border-base-700 text-slate-300 hover:bg-base-800'
            )}
          >
            {item}
          </button>
        ))}
        <button
          type="button"
          disabled={page === pages}
          onClick={() => onPageChange(page + 1)}
          className="rounded-md border border-base-700 px-2.5 py-1 text-xs text-slate-300 transition-colors hover:bg-base-800 disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}
