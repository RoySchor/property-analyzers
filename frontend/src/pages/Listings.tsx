import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, type Listing } from '../api/client';
import { Card, Delta, Empty, ErrorBanner, Loading, MapLink, SortTh, Td } from '../components/ui';
import MaxSlider from '../components/MaxSlider';
import SearchBox from '../components/SearchBox';
import { inputClass } from '../components/styles';
import { useAsync } from '../components/useAsync';
import { useDebounced } from '../components/useDebounced';
import { useSortable, type Accessors } from '../components/useSortable';
import { compactMoney, googleMapsUrl, money, num, shortDate, signedPct, titleCase } from '../format';

const TYPES = ['', 'single_family', 'multi_family', 'townhomes', 'condos', 'apartment'];

const ACCESSORS: Accessors<Listing> = {
  address: (l) => l.address,
  type: (l) => l.property_type,
  price: (l) => l.list_price,
  beds: (l) => l.beds,
  sqft: (l) => l.sqft,
  last_sold: (l) => l.prev_sale_date,
  change: (l) => l.change_since_sale_pct,
  zip_change: (l) => l.zip_change_same_period_pct,
  tax: (l) => l.annual_tax,
  rent: (l) => l.rent,
  cashflow: (l) => l.monthly_cashflow,
};

export default function Listings({ garageOnly = false }: { garageOnly?: boolean }) {
  const [params, setParams] = useSearchParams();
  const zips = params.get('zips') ?? '';
  const propertyType = params.get('type') ?? '';
  const status = params.get('status') ?? 'active';
  const [search, setSearch] = useState('');
  const [maxPrice, setMaxPrice] = useState<number | null>(null);
  const q = useDebounced(search.trim());

  const regions = useAsync(() => api.regions(), []);
  const { data, error, loading, reload } = useAsync(
    () => api.listings({ zips, property_type: propertyType, status, garage_only: garageOnly, q }),
    [zips, propertyType, status, garageOnly, q],
  );
  const suggestions = useMemo(
    () => [...new Set((data?.listings ?? []).map((l) => l.address).filter((a): a is string => Boolean(a)))].map((value) => ({ value })),
    [data],
  );
  const allListings = useMemo(() => data?.listings ?? [], [data]);
  const priceCeiling = useMemo(() => Math.max(0, ...allListings.map((l) => l.list_price ?? 0)), [allListings]);
  const visibleListings = useMemo(
    () => (maxPrice === null ? allListings : allListings.filter((l) => (l.list_price ?? 0) <= maxPrice)),
    [allListings, maxPrice],
  );
  const { sorted, sort } = useSortable(visibleListings, ACCESSORS, { key: 'price', dir: 'desc' });
  const zipOptions = useMemo(
    () => (regions.data?.regions ?? []).filter((r) => r.is_active).flatMap((r) => r.zips.map((z) => ({ zip: z, region: r.name }))),
    [regions.data],
  );

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <SearchBox value={search} onChange={setSearch} suggestions={suggestions} placeholder="Search by address…" />
        <select className={inputClass} value={zips} onChange={(e) => update('zips', e.target.value)}>
          <option value="">All tracked ZIPs</option>
          {(regions.data?.regions ?? []).filter((r) => r.is_active).map((r) => (
            <option key={r.id} value={r.zips.join(',')}>{r.name} (all)</option>
          ))}
          {zipOptions.map((o) => <option key={o.zip} value={o.zip}>{o.zip} · {o.region}</option>)}
        </select>
        <select className={inputClass} value={propertyType} onChange={(e) => update('type', e.target.value)}>
          {TYPES.map((t) => <option key={t} value={t}>{t ? titleCase(t) : 'All property types'}</option>)}
        </select>
        <select className={inputClass} value={status} onChange={(e) => update('status', e.target.value)}>
          <option value="active">Active + pending</option>
          <option value="for_sale">For sale only</option>
          <option value="off_market">Gone off market</option>
          <option value="all">All</option>
        </select>
      </div>
      <div className="flex justify-center">
        <MaxSlider
          label="Max price"
          ceiling={priceCeiling}
          value={maxPrice}
          onChange={setMaxPrice}
          format={compactMoney}
          shown={visibleListings.length}
          total={allListings.length}
          noun="listings"
        />
      </div>

      {error && <ErrorBanner message={error} onRetry={reload} />}
      <Card
        title={garageOnly ? 'Listings with garages or parking' : `Listings ≤ ${compactMoney(data?.max_price)}`}
        subtitle="Realtor.com via HomeHarvest, matched to county parcels for sale history and real taxes. Cash flow uses your Settings. Click a column header to sort."
      >
        {loading ? <Loading /> : !sorted.length ? (
          <Empty>{maxPrice !== null && allListings.length ? `No listings at or under ${compactMoney(maxPrice)} — drag the price slider right.` : q ? `No listings match “${q}”.` : 'No listings match. They load during sync — check the sync status in the top bar.'}</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <SortTh label="Address" sortKey="address" sort={sort} />
                  <th className="px-2 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Map</th>
                  <SortTh label="Type" sortKey="type" sort={sort} />
                  <SortTh label="Price" sortKey="price" sort={sort} right />
                  <SortTh label="Beds" sortKey="beds" sort={sort} right />
                  <SortTh label="Sqft" sortKey="sqft" sort={sort} right />
                  <SortTh label="Last sold" sortKey="last_sold" sort={sort} right />
                  <SortTh label="Change since" sortKey="change" sort={sort} right hint="Asking price vs. the last time this property sold" />
                  <SortTh label="ZIP same period" sortKey="zip_change" sort={sort} right hint="How much typical home values in this ZIP changed over the same period — compare with Change since" />
                  <SortTh label="Tax/yr" sortKey="tax" sort={sort} right />
                  <SortTh label="Rent/mo" sortKey="rent" sort={sort} right />
                  <SortTh label="Cash flow" sortKey="cashflow" sort={sort} right hint="Monthly rent minus mortgage, tax, insurance, HOA, vacancy, maintenance, CapEx and management (your Settings)" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {sorted.map((l) => (
                  <tr key={l.listing_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <Td>
                      <Link to={`/listing/${l.listing_id}`} className="font-medium text-blue-600 hover:underline dark:text-blue-400">
                        {l.address ?? 'Unknown address'}
                      </Link>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {l.city} {l.zip} · {l.status === 'for_sale' ? 'For sale' : titleCase(l.status)}
                        {l.has_garage ? ' · garage' : ''}
                      </div>
                    </Td>
                    <Td><MapLink url={googleMapsUrl(l.address, l.city, `PA ${l.zip}`)} /></Td>
                    <Td>{titleCase(l.property_type)}</Td>
                    <Td right>{money(l.list_price)}</Td>
                    <Td right>{num(l.beds)}/{num(l.baths, 1)}</Td>
                    <Td right>{num(l.sqft)}</Td>
                    <Td right>
                      {l.prev_sale_price ? <>{compactMoney(l.prev_sale_price)}<div className="text-xs text-gray-500">{shortDate(l.prev_sale_date)}</div></> : '—'}
                    </Td>
                    <Td right>{signedPct(l.change_since_sale_pct, 0)}</Td>
                    <Td right>{signedPct(l.zip_change_same_period_pct, 0)}</Td>
                    <Td right>
                      {money(l.annual_tax)}
                      <div className="text-xs text-gray-500">{l.tax_source === 'county_millage' ? 'county' : 'estimate'}</div>
                    </Td>
                    <Td right>{l.rent ? money(l.rent) : <span className="text-xs text-gray-500">needs estimate</span>}</Td>
                    <Td right><Delta value={l.monthly_cashflow} text={money(l.monthly_cashflow)} /></Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
