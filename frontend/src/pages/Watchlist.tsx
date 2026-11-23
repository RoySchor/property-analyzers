import { Link } from 'react-router-dom';
import { api, type WatchItem } from '../api/client';
import { Card, Empty, ErrorBanner, Loading, SortTh, Td } from '../components/ui';
import { ghostButtonClass } from '../components/styles';
import { useAsync } from '../components/useAsync';
import { useSortable, type Accessors } from '../components/useSortable';
import { money, shortDate, titleCase } from '../format';

const ACCESSORS: Accessors<WatchItem> = {
  address: (w) => w.address ?? w.parcel_address,
  status: (w) => w.status,
  price: (w) => w.list_price,
  cashflow: (w) => w.monthly_cashflow,
  last_sold: (w) => w.last_sale_date,
};

export default function Watchlist() {
  const { data, error, loading, reload } = useAsync(() => api.watchlist(), []);
  const { sorted, sort } = useSortable(data?.items ?? [], ACCESSORS, { key: 'price', dir: 'desc' });

  const remove = async (id: number) => {
    try {
      await api.removeWatch(id);
      reload();
    } catch {
      reload();
    }
  };

  if (loading) return <Loading />;
  return (
    <Card title="Watchlist" subtitle="Saved listings. Prices and status update on each sync.">
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {!sorted.length ? <Empty>Nothing saved yet — use "Add to watchlist" on a listing.</Empty> : (
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead>
            <tr>
              <SortTh label="Address" sortKey="address" sort={sort} />
              <SortTh label="Status" sortKey="status" sort={sort} />
              <SortTh label="Price" sortKey="price" sort={sort} right />
              <SortTh label="Cash flow" sortKey="cashflow" sort={sort} right />
              <SortTh label="Last sold" sortKey="last_sold" sort={sort} right />
              <th />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {sorted.map((item) => (
              <tr key={item.id}>
                <Td>
                  {item.listing_id ? (
                    <Link to={`/listing/${item.listing_id}`} className="text-blue-600 hover:underline dark:text-blue-400">{item.address}</Link>
                  ) : item.parcel_address}
                  <div className="text-xs text-gray-500">{item.zip}</div>
                </Td>
                <Td>{titleCase(item.status)}</Td>
                <Td right>{money(item.list_price)}</Td>
                <Td right>{money(item.monthly_cashflow)}</Td>
                <Td right>{item.last_sale_price ? `${money(item.last_sale_price)} · ${shortDate(item.last_sale_date)}` : '—'}</Td>
                <Td><button className={ghostButtonClass} onClick={() => remove(item.id)}>Remove</button></Td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
