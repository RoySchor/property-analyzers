import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Sale } from '../api/client';
import { Card, Empty, ErrorBanner, Loading, MapLink, SortTh, Td } from '../components/ui';
import MaxSlider from '../components/MaxSlider';
import SearchBox from '../components/SearchBox';
import { inputClass } from '../components/styles';
import { useAsync } from '../components/useAsync';
import { useDebounced } from '../components/useDebounced';
import { useSortable, type Accessors } from '../components/useSortable';
import { compactMoney, googleMapsUrl, money, num, shortDate, titleCase } from '../format';

const CLASSES = ['', 'single_family', 'multi_family', 'condo', 'mixed_use', 'garage', 'parking'];

const buyerType = (s: Sale) =>
  s.is_homestead === 0 || s.is_absentee === 1 ? 'Likely investor' : s.is_homestead === 1 ? 'Owner-occupant' : null;

const ACCESSORS: Accessors<Sale> = {
  date: (s) => s.sale_date,
  address: (s) => s.address,
  zip: (s) => s.zip,
  class: (s) => s.property_class,
  price: (s) => s.sale_price,
  sqft: (s) => s.sqft,
  ppsf: (s) => (s.sqft ? s.sale_price / s.sqft : null),
  beds: (s) => s.beds,
  built: (s) => s.year_built,
  tax: (s) => s.annual_tax_est,
  buyer: buyerType,
};

export default function Sales() {
  const [months, setMonths] = useState(6);
  const [underCap, setUnderCap] = useState(true);
  const [propertyClass, setPropertyClass] = useState('');
  const [zips, setZips] = useState('');
  const [search, setSearch] = useState('');
  const [maxPrice, setMaxPrice] = useState<number | null>(null);
  const q = useDebounced(search.trim());
  const regions = useAsync(() => api.regions(), []);
  const { data, error, loading, reload } = useAsync(
    () => api.sales({ months, under_cap: underCap, property_class: propertyClass, zips, q }),
    [months, underCap, propertyClass, zips, q],
  );
  const suggestions = useMemo(
    () => [...new Set((data?.sales ?? []).map((s) => s.address).filter((a): a is string => Boolean(a)))].map((value) => ({ value })),
    [data],
  );
  const allSales = useMemo(() => data?.sales ?? [], [data]);
  const priceCeiling = useMemo(() => Math.max(0, ...allSales.map((s) => s.sale_price)), [allSales]);
  const visibleSales = useMemo(
    () => (maxPrice === null ? allSales : allSales.filter((s) => s.sale_price <= maxPrice)),
    [allSales, maxPrice],
  );
  const { sorted, sort } = useSortable(visibleSales, ACCESSORS, { key: 'price', dir: 'desc' });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <SearchBox value={search} onChange={setSearch} suggestions={suggestions} placeholder="Search by address…" />
        <select className={inputClass} value={zips} onChange={(e) => setZips(e.target.value)}>
          <option value="">All tracked ZIPs</option>
          {(regions.data?.regions ?? []).filter((r) => r.is_active).map((r) => (
            <option key={r.id} value={r.zips.join(',')}>{r.name}</option>
          ))}
        </select>
        <select className={inputClass} value={months} onChange={(e) => setMonths(Number(e.target.value))}>
          {[3, 6, 12, 24, 60].map((m) => <option key={m} value={m}>Last {m} months</option>)}
        </select>
        <select className={inputClass} value={propertyClass} onChange={(e) => setPropertyClass(e.target.value)}>
          {CLASSES.map((c) => <option key={c} value={c}>{c ? titleCase(c) : 'All property classes'}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
          <input type="checkbox" checked={underCap} onChange={(e) => setUnderCap(e.target.checked)} /> Under my price cap
        </label>
      </div>
      <div className="flex justify-center">
        <MaxSlider
          label="Max price"
          ceiling={priceCeiling}
          value={maxPrice}
          onChange={setMaxPrice}
          format={compactMoney}
          shown={visibleSales.length}
          total={allSales.length}
          noun="sales"
        />
      </div>
      {error && <ErrorBanner message={error} onRetry={reload} />}
      <Card title="Recorded sales" subtitle="County assessment records, arm's-length sales only. Investor buyers = buyer doesn't claim homestead or mails elsewhere.">
        {loading ? <Loading /> : !sorted.length ? <Empty>{maxPrice !== null && allSales.length ? `No sales at or under ${compactMoney(maxPrice)} — drag the price slider right.` : q ? `No sales match “${q}” with these filters.` : 'No sales match.'}</Empty> : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <SortTh label="Date" sortKey="date" sort={sort} />
                  <SortTh label="Address" sortKey="address" sort={sort} />
                  <th className="px-2 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Map</th>
                  <SortTh label="ZIP" sortKey="zip" sort={sort} />
                  <SortTh label="Class" sortKey="class" sort={sort} />
                  <SortTh label="Price" sortKey="price" sort={sort} right />
                  <SortTh label="Sqft" sortKey="sqft" sort={sort} right />
                  <SortTh label="$/sqft" sortKey="ppsf" sort={sort} right />
                  <SortTh label="Beds" sortKey="beds" sort={sort} right />
                  <SortTh label="Built" sortKey="built" sort={sort} right />
                  <SortTh label="Tax/yr" sortKey="tax" sort={sort} right />
                  <SortTh label="Buyer" sortKey="buyer" sort={sort} />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {sorted.map((s) => (
                  <tr key={s.id}>
                    <Td>{shortDate(s.sale_date)}</Td>
                    <Td><Link to={`/sale/${s.id}`} className="font-medium text-blue-600 hover:underline dark:text-blue-400">{s.address ?? 'Unknown address'}</Link></Td>
                    <Td><MapLink url={googleMapsUrl(s.address, `PA ${s.zip}`)} /></Td>
                    <Td>{s.zip}</Td>
                    <Td>{titleCase(s.property_class)}</Td>
                    <Td right>{money(s.sale_price)}</Td>
                    <Td right>{num(s.sqft)}</Td>
                    <Td right>{s.sqft ? money(s.sale_price / s.sqft) : '—'}</Td>
                    <Td right>{num(s.beds)}</Td>
                    <Td right>{s.year_built ?? '—'}</Td>
                    <Td right>{money(s.annual_tax_est)}</Td>
                    <Td>{buyerType(s) ?? '—'}</Td>
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
