import type { ReactNode } from 'react';
import type { SortState } from './useSortable';

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
      <span>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="rounded bg-red-600 px-3 py-1 text-white hover:bg-red-700">
          Retry
        </button>
      )}
    </div>
  );
}

export function Card({ title, subtitle, children, actions }: { title?: string; subtitle?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      {(title || actions) && (
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">{title}</h2>}
            {subtitle && <p className="text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</div>
      <div className="tabular mt-1 text-2xl font-semibold text-gray-900 dark:text-gray-100">{value}</div>
      {hint && <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</div>}
    </div>
  );
}

export function Loading() {
  return <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">Loading…</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">{children}</div>;
}


export function Th({ children, right }: { children: ReactNode; right?: boolean }) {
  return (
    <th className={`whitespace-nowrap px-2 py-2 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400 ${right ? 'text-right' : 'text-left'}`}>
      {children}
    </th>
  );
}

export function Td({ children, right, className = '' }: { children: ReactNode; right?: boolean; className?: string }) {
  return (
    <td className={`whitespace-nowrap px-2 py-2 text-sm text-gray-800 dark:text-gray-200 ${right ? 'tabular text-right' : ''} ${className}`}>
      {children}
    </td>
  );
}

export function Delta({ value, text }: { value: number | null | undefined; text: string }) {
  if (value === null || value === undefined) return <span className="text-gray-400">—</span>;
  const tone = value >= 0 ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400';
  return <span className={`tabular ${tone}`}>{value >= 0 ? '▲' : '▼'} {text}</span>;
}

/** Clickable column header. Shows ↕ when unsorted, ▲/▼ for the active column. */
export function SortTh({ label, sortKey, sort, right, hint }: { label: ReactNode; sortKey: string; sort: SortState; right?: boolean; hint?: string }) {
  const active = sort.key === sortKey;
  const ariaSort = active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';
  return (
    <th aria-sort={ariaSort} className={`whitespace-nowrap px-2 py-2 ${right ? 'text-right' : 'text-left'}`}>
      <button
        type="button"
        onClick={() => sort.toggle(sortKey)}
        className={`inline-flex items-center gap-1 text-xs font-medium uppercase tracking-wide hover:text-gray-900 dark:hover:text-gray-100 ${
          active ? 'text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400'
        } ${right ? 'flex-row-reverse' : ''}`}
        title={`Sort by ${typeof label === 'string' ? label.toLowerCase() : 'this column'}`}
      >
        <span>{label}</span>
        {hint && (
          <span title={hint} aria-label={hint} className="cursor-help normal-case text-gray-400">ⓘ</span>
        )}
        <span aria-hidden className={`text-[0.625rem] ${active ? '' : 'opacity-40'}`}>
          {active ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  );
}

export function MapLink({ url }: { url: string | null }) {
  if (!url) return <span className="text-gray-400">—</span>;
  return (
    <a href={url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline dark:text-blue-400">
      Map
    </a>
  );
}
