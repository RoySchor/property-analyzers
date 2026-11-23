import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Parcel } from '../api/client';
import { Card, Empty, ErrorBanner, Loading, MapLink, SortTh, Td } from '../components/ui';
import MaxSlider from '../components/MaxSlider';
import SearchBox, { type Suggestion } from '../components/SearchBox';
import { inputClass } from '../components/styles';
import { useAsync } from '../components/useAsync';
import { useDebounced } from '../components/useDebounced';
import { useSortable, type Accessors } from '../components/useSortable';
import { compactMoney, googleMapsUrl, money, shortDate, titleCase } from '../format';
import Listings from './Listings';

const GARAGE_CLASSES = [
  ['garage', 'Detached garages / outbuildings'],
  ['parking', 'Parking lots & decks'],
  ['auto_garage', 'Commercial repair garages'],
  ['storage', 'Mini-storage'],
] as const;

const ACCESSORS: Accessors<Parcel> = {
  address: (p) => p.address,
  zip: (p) => p.zip,
  class: (p) => p.property_class,
  sale_price: (p) => p.last_sale_price,
  sale_date: (p) => p.last_sale_date,
  assessed: (p) => p.assessed_value,
  tax: (p) => p.annual_tax_est,
  owner: (p) => p.owner_name,
};

export default function Garages() {
  const [propertyClass, setPropertyClass] = useState<string>('garage');
  const [zips, setZips] = useState('');
  const [search, setSearch] = useState('');
  const [maxAssessed, setMaxAssessed] = useState<number | null>(null);
  const q = useDebounced(search.trim());
  const regions = useAsync(() => api.regions(), []);
  const defaultZips = (regions.data?.regions ?? []).filter((r) => r.is_active).flatMap((r) => r.zips).join(',');
  const effectiveZips = zips || defaultZips;
  const parcels = useAsync(
    () => (effectiveZips ? api.parcels({ zips: effectiveZips, property_class: propertyClass, q }) : Promise.resolve({ parcels: [] })),
    [effectiveZips, propertyClass, q],
  );
  const suggestions = useMemo(() => {
    const seen = new Set<string>();
    const out: Suggestion[] = [];
    for (const p of parcels.data?.parcels ?? []) {
      for (const [value, hint] of [[p.address, 'address'], [p.owner_name, 'owner']] as const) {
        if (value && !seen.has(`${hint}:${value}`)) {
          seen.add(`${hint}:${value}`);
          out.push({ value, hint });
        }
      }
    }
    return out;
  }, [parcels.data]);
  const allParcels = useMemo(() => parcels.data?.parcels ?? [], [parcels.data]);
  const assessedCeiling = useMemo(() => Math.max(0, ...allParcels.map((p) => p.assessed_value ?? 0)), [allParcels]);
  const visibleParcels = useMemo(
    // Parcels with no assessed value stay visible only when the slider is off.
    () => (maxAssessed === null ? allParcels : allParcels.filter((p) => p.assessed_value !== null && p.assessed_value <= maxAssessed)),
    [allParcels, maxAssessed],
  );
  const { sorted, sort } = useSortable(visibleParcels, ACCESSORS, { key: 'sale_price', dir: 'desc' });

  return (
    <div className="space-y-6">
      <Listings garageOnly />
      <Card
        title="Garage & parking parcels"
        subtitle="Stand-alone county parcels. These rarely appear on listing sites — check owners for off-market offers. LoopNet / Crexi have no free API. Click a column header to sort."
        actions={
          <div className="flex flex-wrap gap-2">
            <SearchBox value={search} onChange={setSearch} suggestions={suggestions} placeholder="Search address or owner…" />
            <select className={inputClass} value={zips} onChange={(e) => setZips(e.target.value)}>
              <option value="">All tracked ZIPs</option>
              {(regions.data?.regions ?? []).filter((r) => r.is_active).map((r) => <option key={r.id} value={r.zips.join(',')}>{r.name}</option>)}
            </select>
            <select className={inputClass} value={propertyClass} onChange={(e) => setPropertyClass(e.target.value)}>
              {GARAGE_CLASSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        }
      >
        {parcels.error && <ErrorBanner message={parcels.error} onRetry={parcels.reload} />}
        <div className="mb-3 flex justify-center">
          <MaxSlider
            label="Max assessed value"
            ceiling={assessedCeiling}
            value={maxAssessed}
            onChange={setMaxAssessed}
            format={compactMoney}
            shown={visibleParcels.length}
            total={allParcels.length}
          noun="parcels"
          />
        </div>
        {parcels.loading ? <Loading /> : !sorted.length ? <Empty>{maxAssessed !== null && allParcels.length ? `No parcels assessed at or under ${compactMoney(maxAssessed)} — drag the slider right.` : q ? `No parcels match “${q}”.` : 'No parcels of this type in the selected ZIPs.'}</Empty> : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <SortTh label="Address" sortKey="address" sort={sort} />
                  <th className="px-2 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Map</th>
                  <SortTh label="ZIP" sortKey="zip" sort={sort} />
                  <SortTh label="Class" sortKey="class" sort={sort} />
                  <SortTh label="Last sale" sortKey="sale_price" sort={sort} right />
                  <SortTh label="Sale date" sortKey="sale_date" sort={sort} right />
                  <SortTh label="Assessed" sortKey="assessed" sort={sort} right />
                  <SortTh label="Tax/yr" sortKey="tax" sort={sort} right />
                  <SortTh label="Owner" sortKey="owner" sort={sort} />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {sorted.map((p) => (
                  <tr key={p.parcel_id}>
                    <Td>
                      <Link to={`/parcel/${encodeURIComponent(p.parcel_id)}`} className="font-medium text-blue-600 hover:underline dark:text-blue-400">
                        {p.address ?? p.parcel_id}
                      </Link>
                    </Td>
                    <Td><MapLink url={p.address ? googleMapsUrl(p.address, `PA ${p.zip ?? ''}`.trim()) : null} /></Td>
                    <Td>{p.zip}</Td>
                    <Td>{titleCase(p.property_class)}</Td>
                    <Td right>{p.last_sale_valid ? money(p.last_sale_price) : <span className="text-gray-400">{money(p.last_sale_price)}*</span>}</Td>
                    <Td right>{shortDate(p.last_sale_date)}</Td>
                    <Td right>{money(p.assessed_value)}</Td>
                    <Td right>{money(p.annual_tax_est)}</Td>
                    <Td>{p.owner_name}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-gray-500">* non-market transfer. Lehigh's garage code (1110) is inferred from the data, not from an official code table.</p>
          </div>
        )}
      </Card>
    </div>
  );
}
