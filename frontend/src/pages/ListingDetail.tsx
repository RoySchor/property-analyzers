import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, type ListingDetail as ListingDetailData } from '../api/client';
import PhotoGallery from '../components/PhotoGallery';
import TrendChart from '../components/TrendChart';
import { Card, ErrorBanner, Loading, SortTh, StatTile, Td } from '../components/ui';
import { buttonClass, ghostButtonClass } from '../components/styles';
import { useAsync } from '../components/useAsync';
import { useSortable, type Accessors } from '../components/useSortable';
import { compactMoney, money, num, pct, shortDate, signedPct, titleCase } from '../format';

interface HistoryRow {
  key: string;
  date: string;
  event: string;
  amount: number | null;
}

type Comp = ListingDetailData['comps'][number];

const HISTORY_ACCESSORS: Accessors<HistoryRow> = {
  date: (r) => r.date,
  event: (r) => r.event,
  amount: (r) => r.amount,
};

const COMP_ACCESSORS: Accessors<Comp> = {
  date: (c) => c.sale_date,
  address: (c) => c.address,
  price: (c) => c.sale_price,
  sqft: (c) => c.sqft,
  ppsf: (c) => (c.sqft ? c.sale_price / c.sqft : null),
};

function historyRows(data: ListingDetailData | null): HistoryRow[] {
  if (!data) return [];
  return [
    ...data.sales_history.map((s, i) => ({
      key: `s${i}`, date: s.sale_date, amount: s.sale_price,
      event: `Sold${s.is_valid ? '' : ' (non-market transfer)'} · ${s.source}`,
    })),
    ...data.parcel_history.map((h) => ({
      key: `p${h.captured_at}`, date: h.captured_at, amount: h.assessed_value, event: 'County record captured (assessed)',
    })),
    ...data.price_history.map((p) => ({
      key: `l${p.captured_at}`, date: p.captured_at, amount: p.list_price, event: `Listing ${titleCase(p.status)}`,
    })),
  ];
}

export default function ListingDetail() {
  const { id = '' } = useParams();
  const { data, error, loading, reload } = useAsync(() => api.listing(id), [id]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const history = useMemo(() => historyRows(data), [data]);
  const historyTable = useSortable(history, HISTORY_ACCESSORS, { key: 'date', dir: 'asc' });
  const compTable = useSortable(data?.comps ?? [], COMP_ACCESSORS, { key: 'price', dir: 'desc' });

  if (loading) return <Loading />;
  if (error || !data) return <ErrorBanner message={error ?? 'Not found'} onRetry={reload} />;

  const { listing: l, parcel } = data;
  const fetchRent = async () => {
    setBusy(true);
    setActionError(null);
    try {
      await api.rentEstimate(id);
      reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const watch = async () => {
    try {
      await api.addWatch({ listing_id: id });
      setSaved(true);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };

  const zipSeries = data.zip_value_series.filter((p) => !l.prev_sale_date || p.period >= l.prev_sale_date.slice(0, 4) + '-01-01');

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/listings" className="text-sm text-blue-600 hover:underline dark:text-blue-400">← Listings</Link>
          <h1 className="mt-1 text-2xl font-semibold text-gray-900 dark:text-gray-100">{l.address}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {l.city}, PA {l.zip} · {titleCase(l.property_type)} · {titleCase(l.status)} · listed {shortDate(l.list_date)}
          </p>
        </div>
        <div className="flex gap-2">
          {l.url && <a href={l.url} target="_blank" rel="noreferrer" className={ghostButtonClass}>Realtor.com ↗</a>}
          <button onClick={watch} disabled={saved} className={ghostButtonClass}>{saved ? 'Saved ✓' : 'Add to watchlist'}</button>
          <button
            onClick={fetchRent}
            disabled={busy || data.rentcast.used >= data.rentcast.cap}
            className={buttonClass}
            title="Uses 1 RentCast call. Hard limit: 45 per rolling 31 days (free tier is 50 per billing period)."
          >
            {busy ? 'Fetching…' : data.rentcast.used >= data.rentcast.cap ? 'RentCast limit reached' : `RentCast rent (${data.rentcast.used}/${data.rentcast.cap} used, 31 days)`}
          </button>
        </div>
      </div>
      {actionError && <ErrorBanner message={actionError} />}

      <PhotoGallery key={l.listing_id} photos={l.photos ?? []} alt={l.address ?? 'Listing'} />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Asking" value={money(l.list_price)} hint={l.sqft ? `${money(l.price_per_sqft)}/sqft · comps ${money(l.comp_price_per_sqft)}/sqft` : undefined} />
        <StatTile
          label="Last sold"
          value={l.prev_sale_price ? money(l.prev_sale_price) : '—'}
          hint={l.prev_sale_price ? `${shortDate(l.prev_sale_date)} · ${signedPct(l.change_since_sale_pct, 0)} to asking (ZIP ${signedPct(l.zip_change_same_period_pct, 0)})` : 'No prior sale found'}
        />
        <StatTile label="Monthly cash flow" value={money(l.monthly_cashflow)} hint={`Cash-on-cash ${pct(l.cash_on_cash)}`} />
        <StatTile label="Est. rent / month" value={money(l.rent)} hint={l.rent_source ?? undefined} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Deal math" subtitle="Assumptions come from Settings">
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <Row label="Rent / month" value={money(l.rent)} note={l.rent_source} />
            <Row label="Mortgage + tax + insurance" value={money(l.monthly_piti)} />
            <Row label="Property tax / year" value={money(l.annual_tax)} note={l.tax_source === 'county_millage' ? 'County assessment × 2026 millage' : 'Estimate (no county millage)'} />
            <Row label="HOA / month" value={money(l.hoa_fee)} />
            <Row label="Cash-on-cash" value={pct(l.cash_on_cash)} />
          </dl>
        </Card>

        <Card title="Value since last sale" subtitle={`Zillow typical value for ${l.zip}${l.prev_sale_date ? ` since ${l.prev_sale_date.slice(0, 4)}` : ''}`}>
          <TrendChart series={[{ key: 'zip', label: `ZIP ${l.zip}`, colorIndex: 0, points: zipSeries }]} format={compactMoney} height={220} />
          {l.prev_sale_price && (
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              Asking is <span className="tabular font-medium">{signedPct(l.change_since_sale_pct, 0)}</span> vs. its {shortDate(l.prev_sale_date)} sale;
              the ZIP moved {signedPct(l.zip_change_same_period_pct, 0)} over the same period.
            </p>
          )}
        </Card>

        <Card title="County record" subtitle={parcel ? `Parcel ${parcel.parcel_id} · matched by ${l.match_method}` : 'Not matched to a county parcel'}>
          {parcel ? (
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <Row label="Class / land use" value={`${titleCase(parcel.property_class)} (${parcel.land_use_code})`} />
              <Row label="Assessed value" value={money(parcel.assessed_value)} note={parcel.county_fips === '42095' ? '1995 base year' : '2013 base year'} />
              <Row label="Annual tax (est.)" value={money(parcel.annual_tax_est)} />
              <Row label="Owner" value={parcel.owner_name ?? '—'} />
              <Row label="Owner-occupied" value={parcel.is_homestead === null ? '—' : parcel.is_homestead ? 'Yes (homestead)' : 'No'} />
              <Row label="Beds / baths / sqft" value={`${num(parcel.beds)} / ${num(parcel.baths, 1)} / ${num(parcel.sqft)}`} />
              <Row label="Year built" value={String(parcel.year_built ?? '—')} />
            </dl>
          ) : (
            <p className="text-sm text-gray-500">The address didn't match county records, so sale history and real taxes are unavailable.</p>
          )}
        </Card>

        <Card title="Sale, value and price history">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                <SortTh label="Date" sortKey="date" sort={historyTable.sort} />
                <SortTh label="Event" sortKey="event" sort={historyTable.sort} />
                <SortTh label="Amount" sortKey="amount" sort={historyTable.sort} right />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {historyTable.sorted.map((row) => (
                <tr key={row.key}><Td>{shortDate(row.date)}</Td><Td>{row.event}</Td><Td right>{money(row.amount)}</Td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <Card title="Nearby comparable sales" subtitle={`Valid county sales in ${l.zip}, last 12 months, closest in price`}>
        <table className="min-w-full">
          <thead>
            <tr>
              <SortTh label="Date" sortKey="date" sort={compTable.sort} />
              <SortTh label="Address" sortKey="address" sort={compTable.sort} />
              <SortTh label="Price" sortKey="price" sort={compTable.sort} right />
              <SortTh label="Sqft" sortKey="sqft" sort={compTable.sort} right />
              <SortTh label="$/sqft" sortKey="ppsf" sort={compTable.sort} right />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {compTable.sorted.map((c, i) => (
              <tr key={i}>
                <Td>{shortDate(c.sale_date)}</Td><Td>{c.address}</Td><Td right>{money(c.sale_price)}</Td>
                <Td right>{num(c.sqft)}</Td><Td right>{c.sqft ? money(c.sale_price / c.sqft) : '—'}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function Row({ label, value, note }: { label: string; value: string; note?: string | null }) {
  return (
    <>
      <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="tabular text-right text-gray-900 dark:text-gray-100">
        {value}
        {note && <div className="text-xs text-gray-500 dark:text-gray-400">{note}</div>}
      </dd>
    </>
  );
}
