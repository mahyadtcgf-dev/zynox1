import { type ReactNode } from 'react';
import { clsx } from 'clsx';

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  className?: string;
  sortable?: boolean;
}

export function Table<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  empty,
  className,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  empty?: ReactNode;
  className?: string;
}) {
  if (rows.length === 0) {
    return (
      <div className="px-5 py-12 text-center text-sm text-muted">
        {empty ?? 'No records found.'}
      </div>
    );
  }

  return (
    <div className={clsx('overflow-x-auto', className)}>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-base-700 text-left">
            {columns.map((column) => (
              <th
                key={column.key}
                className={clsx(
                  'whitespace-nowrap px-4 py-2.5 text-xxs font-semibold uppercase tracking-wide text-muted',
                  column.className
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={() => onRowClick?.(row)}
              className={clsx(
                'border-b border-base-800 transition-colors',
                onRowClick ? 'cursor-pointer hover:bg-base-800/60' : 'hover:bg-base-800/40'
              )}
            >
              {columns.map((column) => (
                <td key={column.key} className={clsx('px-4 py-3 text-slate-300', column.className)}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
