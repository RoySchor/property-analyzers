import { useMemo, useState } from 'react';

export type SortDir = 'asc' | 'desc';
export type SortValue = string | number | null | undefined;
export type Accessors<T> = Record<string, (row: T) => SortValue>;

export interface SortState {
  key: string | null;
  dir: SortDir;
  toggle: (key: string) => void;
}

/** Client-side column sorting. Empty values always sort last, in either direction. */
export function useSortable<T>(rows: T[], accessors: Accessors<T>, initial?: { key: string; dir: SortDir }) {
  const [key, setKey] = useState<string | null>(initial?.key ?? null);
  const [dir, setDir] = useState<SortDir>(initial?.dir ?? 'asc');

  const sorted = useMemo(() => {
    const accessor = key ? accessors[key] : undefined;
    if (!accessor) return rows;
    const factor = dir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const left = accessor(a);
      const right = accessor(b);
      const leftEmpty = left === null || left === undefined || left === '';
      const rightEmpty = right === null || right === undefined || right === '';
      if (leftEmpty || rightEmpty) return leftEmpty === rightEmpty ? 0 : leftEmpty ? 1 : -1;
      if (typeof left === 'number' && typeof right === 'number') return (left - right) * factor;
      return String(left).localeCompare(String(right), undefined, { numeric: true }) * factor;
    });
    // accessors is a stable object literal per render; key/dir/rows drive recomputation
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, key, dir]);

  const toggle = (next: string) => {
    if (next === key) {
      setDir(dir === 'asc' ? 'desc' : 'asc');
    } else {
      setKey(next);
      setDir('asc');
    }
  };

  const state: SortState = { key, dir, toggle };
  return { sorted, sort: state };
}
