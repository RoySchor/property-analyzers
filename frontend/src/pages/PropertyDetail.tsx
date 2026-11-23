import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, type PropertyDetail as PropertyDetailData } from '../api/client';
import PhotoGallery from '../components/PhotoGallery';
import TrendChart from '../components/TrendChart';
import { Card, ErrorBanner, Loading, MapLink, SortTh, StatTile, Td } from '../components/ui';
import { ghostButtonClass } from '../components/styles';
import { useAsync } from '../components/useAsync';
import { useSortable, type Accessors } from '../components/useSortable';
import { compactMoney, googleMapsUrl, money, num, shortDate, signedPct, titleCase } from '../format';

type HistoryRow = PropertyDetailData['history'][number];
type Comp = PropertyDetailData['comps'][number];

const HISTORY_ACCESSORS: Accessors<HistoryRow> = {
  date: (h) => h.sale_date,
  price: (h) => h.sale_price,
  type: (h) => (h.is_valid ? 'Market sale' : 'Non-market transfer'),
  source: (h) => h.source,
};

const COMP_ACCESSORS: Accessors<Comp> = {
  date: (c) => c.sale_date,
  address: (c) => c.address,
  price: (c) => c.sale_price,
  sqft: (c) => c.sqft,
  ppsf: (c) => (c.sqft ? c.sale_price / c.sqft : null),
  beds: (c) => c.beds,
};

const SOURCE_LABEL: Record<string, string> = { county: 'County record', homeharvest: 'Realtor.com' };

/** Detail page for a recorded sale (/sale/:id) or a county parcel (/parcel/:parcelId, e.g. a garage). */
export default function PropertyDetail() {
  const { id, parcelId } = useParams();
  const { data, error, loading, reload } = useAsync(
    () => (parcelId ? api.parcel(parcelId) : api.sale(id ?? '')),
    [id, parcelId],
  );
  const [saved, setSaved] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const historyTable = useSortable(data?.history ?? [], HISTORY_ACCESSORS, { key: 'date', dir: 'asc' });
  const compTable = useSortable(data?.comps ?? [], COMP_ACCESSORS, { key: 'price', dir: 'desc' });

  if (loading) return <Loading />;
  if (error || !data) return <ErrorBanner message={error ?? 'Not found'} onRetry={reload} />;

  const { sale, parcel, listing } = data;
  const parcelIdForWatch = parcel?.parcel_id ?? sale?.parcel_id ?? null;
  const ppsf = sale && parcel?.sqft ? sale.sale_price / parcel.sqft : null;
  const previous = sale
    ? data.history.filter((h) => h.sale_date < sale.sale_date && h.is_valid && h.source === 'county').at(-1)
    : undefined;
  const changeFromPrevious = sale && previous ? sale.sale_price / previous.sale_price - 1 : null;
  const back = parcelId ? { to: '/garages', label: '← Garages' } : { to: '/sales', label: '← Sales' };

  const watch = async () => {
    if (!parcelIdForWatch) return;
    try {
      await api.addWatch({
        parcel_id: parcelIdForWatch,
        notes: sale ? `Sold ${shortDate(sale.sale_date)} for ${money(sale.sale_price)}` : undefined,
      });
      setSaved(true);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to={back.to} className="text-sm text-blue-600 hover:underline dark:text-blue-400">{back.label}</Link>
          <h1 className="mt-1 text-2xl font-semibold text-gray-900 dark:text-gray-100">{data.address ?? 'Unknown address'}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            PA {data.zip} · {titleCase(parcel?.property_class)}
            {sale ? ` · ${parcelId ? 'last sold' : 'sold'} ${shortDate(sale.sale_date)}` : ' · no recorded sale'}
            {sale && !sale.is_valid && ' · non-market transfer'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {data.links.map((link) => (
            <a key={link.label} href={link.url} target="_blank" rel="noreferrer" className={ghostButtonClass}>
              {link.label} ↗
            </a>
          ))}
          {parcelIdForWatch && (
            <button onClick={watch} disabled={saved} className={ghostButtonClass}>{saved ? 'Saved ✓' : 'Add to watchlist'}</button>
          )}
        </div>
      </div>
      {actionError && <ErrorBanner message={actionError} />}
      {data.parcel_number && (
        <p className="-mt-3 text-xs text-gray-500 dark:text-gray-400">
          Parcel number for the county record search: <span className="select-all font-mono text-gray-700 dark:text-gray-200">{data.parcel_number}</span>
        </p>
      )}

      {listing && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-100">
          {listing.status === 'off_market' ? 'This property was recently listed' : 'This property is currently listed'}
          {listing.list_price ? ` at ${money(listing.list_price)}` : ''} ({titleCase(listing.status)}).{' '}
          <Link to={`/listing/${listing.listing_id}`} className="font-medium underline">See the listing and deal math →</Link>
        </div>
      )}

      {data.photos.length > 0 && <PhotoGallery key={sale?.id ?? parcel?.parcel_id} photos={data.photos} alt={data.address ?? 'Property'} />}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile
          label={parcelId ? 'Last sale price' : 'Sale price'}
          value={sale ? money(sale.sale_price) : '—'}
          hint={sale ? (ppsf ? `${money(ppsf)}/sqft` : shortDate(sale.sale_date)) : 'No recorded sale'}
        />
        <StatTile
          label="Previous sale"
          value={previous ? money(previous.sale_price) : '—'}
          hint={previous ? `${shortDate(previous.sale_date)} · ${signedPct(changeFromPrevious, 0)} to ${parcelId ? 'the last' : 'this'} sale` : 'None on record'}
        />
        <StatTile
          label="Est. value today"
          value={data.estimated_value_today ? money(data.estimated_value_today) : '—'}
          hint={data.zip_change_since_sale !== null ? `ZIP values ${signedPct(data.zip_change_since_sale, 1)} since sale` : 'Not enough ZIP data'}
        />
        <StatTile
          label="Property tax / year"
          value={money(parcel?.annual_tax_est)}
          hint={parcel?.annual_tax_est ? 'County assessment × 2026 millage' : 'No county millage for this parcel'}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Property" subtitle={parcel ? `County parcel ${data.parcel_number}` : 'No county parcel matched'}>
          {parcel ? (
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <Row label="Class / land use" value={`${titleCase(parcel.property_class)} (${parcel.land_use_code ?? '—'})`} />
              <Row label="Beds / baths" value={`${num(parcel.beds ?? listing?.beds)} / ${num(parcel.baths ?? listing?.baths, 1)}`} />
              <Row label="Living area" value={parcel.sqft ? `${num(parcel.sqft)} sqft` : listing?.sqft ? `${num(listing.sqft)} sqft` : '—'} />
              <Row label="Year built" value={String(parcel.year_built ?? listing?.year_built ?? '—')} />
              <Row label="Assessed value" value={money(parcel.assessed_value)} note={parcel.county_fips === '42095' ? '1995 base year' : '2013 base year'} />
              <Row label="Current owner" value={parcel.owner_name ?? '—'} />
              <Row label="Owner mailing address" value={parcel.owner_mail ?? '—'} />
              <Row
                label="Buyer type"
                value={parcel.is_homestead === 0 || parcel.is_absentee === 1 ? 'Likely investor' : parcel.is_homestead === 1 ? 'Owner-occupant' : '—'}
                note="No homestead exemption or mails elsewhere = likely investor"
              />
              <Row label="Map" value="" extra={<MapLink url={googleMapsUrl(data.address, `PA ${data.zip ?? ''}`.trim())} />} />
            </dl>
          ) : (
            <p className="text-sm text-gray-500">No matching county parcel, so property details are limited.</p>
          )}
        </Card>

        <Card title={sale ? 'Value since the sale' : 'ZIP home values'} subtitle={`Zillow typical home value for ${data.zip}`}>
          <TrendChart
            series={[{ key: 'zip', label: `ZIP ${data.zip}`, colorIndex: 0, points: data.zip_value_series }]}
            format={compactMoney}
            height={240}
          />
        </Card>

        <Card title="Sale history" subtitle="Every recorded sale of this property we have">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                <SortTh label="Date" sortKey="date" sort={historyTable.sort} />
                <SortTh label="Price" sortKey="price" sort={historyTable.sort} right />
                <SortTh label="Type" sortKey="type" sort={historyTable.sort} />
                <SortTh label="Source" sortKey="source" sort={historyTable.sort} />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {historyTable.sorted.map((h) => (
                <tr key={h.id} className={h.id === sale?.id ? 'bg-blue-50 dark:bg-blue-950/50' : ''}>
                  <Td>{shortDate(h.sale_date)}</Td>
                  <Td right>{money(h.sale_price)}</Td>
                  <Td>{h.is_valid ? 'Market sale' : 'Non-market transfer'}</Td>
                  <Td>
                    {h.url ? <a href={h.url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline dark:text-blue-400">{SOURCE_LABEL[h.source] ?? h.source} ↗</a> : SOURCE_LABEL[h.source] ?? h.source}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.snapshots.length > 1 && (
            <p className="mt-2 text-xs text-gray-500">{data.snapshots.length} county record changes captured since tracking began.</p>
          )}
        </Card>

        <Card title="Comparable sales" subtitle={`Valid county sales in ${data.zip}${parcel?.property_class ? `, same class (${titleCase(parcel.property_class)})` : ''}, ${data.comps_note}`}>
          {!compTable.sorted.length ? <p className="text-sm text-gray-500">No comparable sales in that window.</p> : (
            <table className="min-w-full text-sm">
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
                {compTable.sorted.map((c) => (
                  <tr key={c.id}>
                    <Td>{shortDate(c.sale_date)}</Td>
                    <Td><Link to={`/sale/${c.id}`} className="text-blue-600 hover:underline dark:text-blue-400">{c.address}</Link></Td>
                    <Td right>{money(c.sale_price)}</Td>
                    <Td right>{num(c.sqft)}</Td>
                    <Td right>{c.sqft ? money(c.sale_price / c.sqft) : '—'}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value, note, extra }: { label: string; value: string; note?: string; extra?: React.ReactNode }) {
  return (
    <>
      <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="tabular text-right text-gray-900 dark:text-gray-100">
        {value}
        {extra}
        {note && <div className="text-xs text-gray-500 dark:text-gray-400">{note}</div>}
      </dd>
    </>
  );
}
