import { useEffect, useState } from 'react';

interface Result<T> {
  key: string;
  data: T | null;
  error: string | null;
}

/** Loads data whenever `deps` change. Keeps the previous data visible while a reload is in flight. */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]) {
  const [token, setToken] = useState(0);
  const [result, setResult] = useState<Result<T> | null>(null);
  const requestKey = `${JSON.stringify(deps)}#${token}`;

  useEffect(() => {
    let cancelled = false;
    load()
      .then((data) => {
        if (!cancelled) setResult({ key: requestKey, data, error: null });
      })
      .catch((e: unknown) => {
        if (!cancelled) setResult((prev) => ({ key: requestKey, data: prev?.data ?? null, error: e instanceof Error ? e.message : String(e) }));
      });
    return () => {
      cancelled = true;
    };
    // `load` is a fresh closure each render; `requestKey` captures everything it depends on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const loading = result === null;
  return {
    data: result?.data ?? null,
    error: result?.key === requestKey ? result.error : null,
    loading,
    refreshing: result?.key !== requestKey,
    reload: () => setToken((t) => t + 1),
  };
}
