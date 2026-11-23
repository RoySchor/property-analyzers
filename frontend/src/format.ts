export const money = (value: number | null | undefined, digits = 0): string =>
  value === null || value === undefined
    ? '—'
    : value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: digits });

export const compactMoney = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '—';
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `$${Math.round(value / 1_000)}k`;
  return `$${Math.round(value)}`;
};

export const pct = (value: number | null | undefined, digits = 1): string =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`;

export const signedPct = (value: number | null | undefined, digits = 1): string =>
  value === null || value === undefined ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`;

export const num = (value: number | null | undefined, digits = 0): string =>
  value === null || value === undefined ? '—' : value.toLocaleString('en-US', { maximumFractionDigits: digits });

export const shortDate = (value: string | null | undefined): string => {
  if (!value) return '—';
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: value.length === 10 ? 'numeric' : undefined });
};

export const monthLabel = (period: string): string => {
  const [year, month] = period.split('-');
  return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(month) - 1]} ${year}`;
};

export const relativeTime = (iso: string | null | undefined): string => {
  if (!iso) return 'never';
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)}h ago`;
  return `${Math.round(minutes / 1440)}d ago`;
};

/** Google Maps search link for a street address or place. Addresses here are public property records. */
export const googleMapsUrl = (...parts: (string | null | undefined)[]): string | null => {
  const query = parts.filter((part) => part && part.trim()).join(', ');
  return query ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}` : null;
};

export const titleCase =(value: string | null | undefined): string =>
  value ? value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '—';
