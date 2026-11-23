import { useState } from 'react';
import { api, type SourceStatus } from '../api/client';
import { Card, ErrorBanner, Loading, SortTh, Td } from '../components/ui';
import { buttonClass, ghostButtonClass } from '../components/styles';
import { useAsync } from '../components/useAsync';
import { useSortable, type Accessors } from '../components/useSortable';
import { num, relativeTime } from '../format';

const STATUS_STYLE: Record<string, string> = {
  ok: 'text-green-700 dark:text-green-400',
  skipped_fresh: 'text-gray-500',
  skipped_unchanged: 'text-gray-500',
  running: 'text-blue-600 dark:text-blue-400',
  needs_key: 'text-amber-700 dark:text-amber-400',
  error: 'text-red-600 dark:text-red-400',
  never: 'text-gray-400',
};
const STATUS_LABEL: Record<string, string> = {
  ok: '✓ Updated',
  skipped_fresh: '✓ Fresh',
  skipped_unchanged: '✓ No changes',
  running: '… Running',
  needs_key: '🔑 Needs key',
  error: '⚠ Failed',
  never: '— Not run',
};

const ACCESSORS: Accessors<SourceStatus> = {
  label: (s) => s.label,
  status: (s) => STATUS_LABEL[s.status] ?? s.status,
  message: (s) => s.message,
  last_success: (s) => s.last_success_at,
  rows: (s) => s.rows_upserted,
};

export default function SyncStatus() {
  const { data, error, loading, reload } = useAsync(() => api.syncStatus(), []);
  const { sorted, sort } = useSortable(data?.sources ?? [], ACCESSORS);
  const [actionError, setActionError] = useState<string | null>(null);

  const trigger = async (force: boolean) => {
    try {
      const result = await api.sync(force);
      if (!result.started) setActionError(result.message);
      setTimeout(reload, 1000);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };

  if (loading) return <Loading />;
  return (
    <Card
      title="Data sources"
      subtitle="Sync runs on every launch. Sources refreshed recently, or whose remote file hasn't changed, are skipped."
      actions={
        <div className="flex gap-2">
          <button className={ghostButtonClass} onClick={reload}>Refresh</button>
          <button className={buttonClass} onClick={() => trigger(false)}>Resync</button>
          <button className={ghostButtonClass} onClick={() => trigger(true)} title="Ignore freshness and re-download everything">Force full resync</button>
        </div>
      }
    >
      {(error || actionError) && <ErrorBanner message={(error || actionError)!} onRetry={reload} />}
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead>
          <tr>
            <SortTh label="Source" sortKey="label" sort={sort} />
            <SortTh label="Status" sortKey="status" sort={sort} />
            <SortTh label="Detail" sortKey="message" sort={sort} />
            <SortTh label="Last success" sortKey="last_success" sort={sort} right />
            <SortTh label="Rows" sortKey="rows" sort={sort} right />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
          {sorted.map((s) => (
            <tr key={s.source}>
              <Td>{s.label}</Td>
              <Td className={STATUS_STYLE[s.status] ?? ''}>{STATUS_LABEL[s.status] ?? s.status}</Td>
              <Td className="max-w-md whitespace-normal text-xs">{s.message}</Td>
              <Td right>{relativeTime(s.last_success_at)}</Td>
              <Td right>{num(s.rows_upserted)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
