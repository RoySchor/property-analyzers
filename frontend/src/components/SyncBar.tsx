import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type SyncStatus } from '../api/client';
import { relativeTime } from '../format';

const POLL_MS = 3000;

/** Top bar: shows resync progress (the backend resyncs on every launch) and a manual Resync button. */
export default function SyncBar() {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const next = await api.syncStatus();
        if (!cancelled) {
          setStatus(next);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
      if (!cancelled) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const resync = async () => {
    try {
      await api.sync();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const errors = status?.sources.filter((s) => s.status === 'error') ?? [];
  const needsKey = status?.sources.filter((s) => s.status === 'needs_key') ?? [];
  const lastFinished = status?.progress.finished_at;

  return (
    <div className="flex flex-wrap items-center gap-3 text-xs">
      {error && <span className="text-red-600 dark:text-red-400">Backend unreachable</span>}
      {status?.progress.running ? (
        <span className="flex items-center gap-2 text-blue-700 dark:text-blue-300">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500" />
          Syncing: {status.progress.current ?? '…'}
        </span>
      ) : (
        <span className="text-gray-500 dark:text-gray-400">Synced {relativeTime(lastFinished)}</span>
      )}
      {errors.length > 0 && (
        <Link to="/sync" className="font-medium text-red-600 hover:underline dark:text-red-400">
          ⚠ {errors.length} source{errors.length > 1 ? 's' : ''} failed
        </Link>
      )}
      {needsKey.length > 0 && (
        <Link to="/sync" className="text-amber-700 hover:underline dark:text-amber-400">
          🔑 {needsKey.length} need{needsKey.length === 1 ? 's' : ''} a key
        </Link>
      )}
      <button
        onClick={resync}
        disabled={status?.progress.running}
        className="rounded-md border border-gray-300 px-2 py-1 text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
      >
        Resync
      </button>
    </div>
  );
}
