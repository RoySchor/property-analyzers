import { useMemo, useState } from 'react';
import { api, type Region, type Series } from '../api/client';
import TrendChart, { type ChartSeries } from '../components/TrendChart';
import { Card, ErrorBanner, Loading, StatTile } from '../components/ui';
import { useAsync } from '../components/useAsync';
import { compactMoney, money, num, pct } from '../format';

const RANGES = [
  { label: '5Y', years: 5 },
  { label: '10Y', years: 10 },
  { label: '20Y', years: 20 },
  { label: 'All', years: 60 },
];

const MAX_ZIP_SERIES = 8; // one per fixed categorical color slot

function startFor(years: number): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().slice(0, 10);
}

function toChartSeries(series: Series[], metric: string, keys: string[], labels: Record<string, string>, colorOf: (key: string) => number) {
  return keys
    .map((key) => series.find((s) => s.geo_id === key && s.metric === metric))
    .filter((s): s is Series => Boolean(s))
    .map<ChartSeries & { colorIndex: number }>((s) => ({
      key: s.geo_id,
      label: labels[s.geo_id] ?? s.geo_id,
      points: s.points,
      colorIndex: colorOf(s.geo_id),
    }));
}

export default function Dashboard() {
  const [regionId, setRegionId] = useState<number | 'all'>('all');
  const [range, setRange] = useState(20);

  const regions = useAsync(() => api.regions(), []);
  const activeRegions: Region[] = useMemo(
    () => (regions.data?.regions ?? []).filter((r) => r.is_active),
    [regions.data],
  );
  const allZips = useMemo(() => [...new Set(activeRegions.flatMap((r) => r.zips))].sort(), [activeRegions]);
  const zips = useMemo(() => {
    const selected = regionId === 'all' ? allZips : activeRegions.find((r) => r.id === regionId)?.zips ?? [];
    return selected.slice(0, MAX_ZIP_SERIES);
  }, [regionId, allZips, activeRegions]);

  // Color follows the ZIP's position in the full tracked list, so filtering never repaints survivors.
  const colorOf = (key: string) => Math.max(0, allZips.indexOf(key)) % 8;
  const labels: Record<string, string> = { US: '30-yr fixed rate' };
  for (const region of activeRegions) for (const zip of region.zips) labels[zip] ??= `${zip} · ${region.name}`;

  const start = startFor(range);
  const zipKey = zips.join(',');
  const zipMetrics = useAsync(
    () => (zips.length ? api.metrics(zips, ['zhvi', 'zhvi_bottom_tier', 'zori'], start) : Promise.resolve({ series: [] })),
    [zipKey, start],
  );
  const inventory = useAsync(
    () => (zips.length ? api.metrics(zips, ['median_days_on_market', 'active_listing_count', 'median_listing_price'], start) : Promise.resolve({ series: [] })),
    [zipKey, start],
  );
  const census = useAsync(
    () => (zips.length ? api.metrics(zips, ['vacancy_rate', 'renter_share', 'median_gross_rent']) : Promise.resolve({ series: [] })),
    [zipKey],
  );
  const macro = useAsync(() => api.metrics(['US'], ['mortgage_30y']), []);
  const settings = useAsync(() => api.settings(), []);
  const maxPrice = Number(settings.data?.settings.max_price ?? 250000);
  const salesTrend = useAsync(
    () => (zips.length ? api.salesTrend(zips, maxPrice) : Promise.resolve({ points: [] })),
    [zipKey, maxPrice],
  );

  const error = regions.error || zipMetrics.error || inventory.error || macro.error;
  if (regions.loading) return <Loading />;

  const zs = zipMetrics.data?.series ?? [];
  const inv = inventory.data?.series ?? [];
  const mac = macro.data?.series ?? [];
  const acs = census.data?.series ?? [];
  const latest = (s?: Series) => s?.points.at(-1)?.value ?? null;
  const mortgage = latest(mac.find((s) => s.metric === 'mortgage_30y'));
  const filteredSales = (salesTrend.data?.points ?? []).filter((p) => p.period >= start);

  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} onRetry={() => { zipMetrics.reload(); inventory.reload(); macro.reload(); }} />}

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1">
          <FilterChip active={regionId === 'all'} onClick={() => setRegionId('all')}>All areas</FilterChip>
          {activeRegions.map((r) => (
            <FilterChip key={r.id} active={regionId === r.id} onClick={() => setRegionId(r.id)}>{r.name}</FilterChip>
          ))}
        </div>
        <div className="ml-auto flex gap-1">
          {RANGES.map((r) => (
            <FilterChip key={r.label} active={range === r.years} onClick={() => setRange(r.years)}>{r.label}</FilterChip>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <StatTile label="30-yr mortgage" value={mortgage ? `${mortgage.toFixed(2)}%` : '—'} hint="Freddie Mac weekly (FRED)" />
        <StatTile label="Your price cap" value={compactMoney(maxPrice)} hint="Change in Settings" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Typical home value" subtitle="Zillow ZHVI, middle tier, by ZIP">
          <TrendChart series={toChartSeries(zs, 'zhvi', zips, labels, colorOf)} format={compactMoney} />
        </Card>
        <Card title="Entry-level home value" subtitle="Zillow ZHVI, bottom third — closest to a ≤ cap budget">
          <TrendChart series={toChartSeries(zs, 'zhvi_bottom_tier', zips, labels, colorOf)} format={compactMoney} />
        </Card>
        <Card title="Typical rent" subtitle="Zillow ZORI, by ZIP (coverage starts later for some ZIPs)">
          <TrendChart series={toChartSeries(zs, 'zori', zips, labels, colorOf)} format={(v) => money(v)} />
        </Card>
        <Card title={`Median valid sale ≤ ${compactMoney(maxPrice)}`} subtitle="County recorded sales (latest sale per parcel), all selected ZIPs, monthly">
          <TrendChart
            series={[{ key: 'median', label: 'Median sale', colorIndex: 0, points: filteredSales.map((p) => ({ period: p.period, value: p.median })) }]}
            format={compactMoney}
          />
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            {num(filteredSales.reduce((sum, p) => sum + p.count, 0))} sales in range. Older months only include parcels that haven't resold since, so early medians are thinner.
          </p>
        </Card>
        <Card title="Median days on market" subtitle="Realtor.com, by ZIP">
          <TrendChart series={toChartSeries(inv, 'median_days_on_market', zips, labels, colorOf)} format={(v) => `${Math.round(v)}d`} />
        </Card>
        <Card title="Active listings" subtitle="Realtor.com inventory, by ZIP">
          <TrendChart series={toChartSeries(inv, 'active_listing_count', zips, labels, colorOf)} format={(v) => num(v)} />
        </Card>
        <Card title="Rental vacancy pressure" subtitle="Census ACS 5-year: vacant share of all housing units, by ZIP">
          <TrendChart series={toChartSeries(acs, 'vacancy_rate', zips, labels, colorOf)} format={(v) => pct(v, 0)} />
        </Card>
        <Card title="Renter share" subtitle="Census ACS 5-year: renter-occupied share of occupied homes — rental demand">
          <TrendChart series={toChartSeries(acs, 'renter_share', zips, labels, colorOf)} format={(v) => pct(v, 0)} />
        </Card>
        <Card title="30-year mortgage rate" subtitle="Freddie Mac PMMS (FRED), weekly">
          <TrendChart
            series={toChartSeries(mac, 'mortgage_30y', ['US'], labels, () => 1)
              .map((s) => ({ ...s, points: s.points.filter((p) => p.period >= start) }))}
            format={(v) => `${v.toFixed(1)}%`}
          />
        </Card>
      </div>
    </div>
  );
}

export function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-sm ${
        active
          ? 'bg-blue-600 text-white'
          : 'border border-gray-300 text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700'
      }`}
    >
      {children}
    </button>
  );
}
