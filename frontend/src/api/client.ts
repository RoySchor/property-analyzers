const BASE = import.meta.env.VITE_API_BASE || '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail ?? parsed);
    } catch {
      // keep raw text
    }
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  return res.json();
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

export interface Region {
  id: number;
  name: string;
  is_default: boolean;
  is_active: boolean;
  zips: string[];
  counties: string[];
}

export interface SeriesPoint {
  period: string;
  value: number;
}

export interface Series {
  geo_id: string;
  geo_type: string;
  metric: string;
  source: string;
  points: SeriesPoint[];
}

export interface Listing {
  listing_id: string;
  parcel_id: string | null;
  match_method: string | null;
  address: string | null;
  city: string | null;
  zip: string;
  property_type: string | null;
  has_garage: number;
  status: string;
  list_price: number;
  list_date: string | null;
  last_sold_price: number | null;
  last_sold_date: string | null;
  estimated_value: number | null;
  beds: number | null;
  baths: number | null;
  sqft: number | null;
  year_built: number | null;
  lot_sqft: number | null;
  hoa_fee: number | null;
  url: string | null;
  photo_url: string | null;
  photos?: string[];          // listing detail only
  first_seen_at: string;
  // deal score
  prev_sale_price: number | null;
  prev_sale_date: string | null;
  change_since_sale_pct: number | null;
  zip_change_same_period_pct: number | null;
  annual_tax: number | null;
  tax_source: string | null;
  rent: number | null;
  rent_source: string | null;
  monthly_piti: number | null;
  monthly_cashflow: number | null;
  cap_rate: number | null;
  cash_on_cash: number | null;
  price_per_sqft: number | null;
  comp_price_per_sqft: number | null;
  score: number | null;
  // parcel
  property_class?: string | null;
  assessed_value?: number | null;
}

export interface Parcel {
  parcel_id: string;
  county_fips: string;
  address: string | null;
  zip: string | null;
  muni: string | null;
  land_use_code: string | null;
  property_class: string | null;
  units: number | null;
  beds: number | null;
  baths: number | null;
  sqft: number | null;
  year_built: number | null;
  owner_name: string | null;
  owner_mail: string | null;
  is_homestead: number | null;
  is_absentee: number | null;
  assessed_value: number | null;
  market_value: number | null;
  last_sale_price: number | null;
  last_sale_date: string | null;
  last_sale_valid: number | null;
  annual_tax_est: number | null;
}

export interface ParcelSnapshot {
  captured_at: string;
  sale_price: number | null;
  sale_date: string | null;
  assessed_value: number | null;
  market_value: number | null;
  owner_name: string | null;
}

export interface Sale {
  id: number;
  parcel_id: string | null;
  address: string | null;
  zip: string;
  sale_date: string;
  sale_price: number;
  is_valid: number;
  source: string;
  property_class?: string | null;
  sqft?: number | null;
  beds?: number | null;
  year_built?: number | null;
  annual_tax_est?: number | null;
  is_homestead?: number | null;
  is_absentee?: number | null;
}

/** Property page payload, shared by /sales/{id} (a recorded sale) and /parcels/{id} (a county parcel). */
export interface PropertyDetail {
  address: string | null;
  zip: string | null;
  sale: (Sale & { url: string | null }) | null;   // null when the parcel has no recorded sale
  parcel: Parcel | null;
  parcel_number: string | null;
  history: { id: number; sale_date: string; sale_price: number; is_valid: number; source: string; url: string | null }[];
  snapshots: ParcelSnapshot[];
  listing: {
    listing_id: string; status: string; list_price: number | null; list_date: string | null; url: string | null;
    beds: number | null; baths: number | null; sqft: number | null; year_built: number | null; lot_sqft: number | null;
  } | null;
  photos: string[];
  zip_value_series: SeriesPoint[];
  zip_change_since_sale: number | null;
  estimated_value_today: number | null;
  comps: { id: number; sale_date: string; sale_price: number; address: string | null; sqft: number | null; beds: number | null; property_class: string | null }[];
  comps_note: string;
  under_cap: boolean | null;
  links: { label: string; url: string }[];
}

export interface ListingDetail {
  listing: Listing;
  price_history: { captured_at: string; list_price: number | null; status: string }[];
  parcel: Parcel | null;
  parcel_history: ParcelSnapshot[];
  sales_history: { sale_date: string; sale_price: number; is_valid: number; source: string }[];
  zip_value_series: SeriesPoint[];
  rent_estimates: { source: string; rent: number; fetched_at: string }[];
  comps: { sale_date: string; sale_price: number; address: string; sqft: number | null; beds: number | null }[];
  rentcast: { used: number; cap: number; window_days: number };
}

export interface SourceStatus {
  source: string;
  label: string;
  status: string;
  message: string | null;
  last_attempt_at: string | null;
  last_success_at: string | null;
  rows_upserted: number | null;
  required_env: string | null;
}

export interface SyncStatus {
  progress: { running: boolean; current: string | null; started_at: string | null; finished_at: string | null };
  sources: SourceStatus[];
}

export interface SettingsResponse {
  settings: Record<string, string>;
  effective_interest_rate_pct: number;
  rentcast: { used: number; cap: number };
}

export interface WatchItem {
  id: number;
  listing_id: string | null;
  parcel_id: string | null;
  notes: string | null;
  created_at: string;
  address: string | null;
  zip: string | null;
  list_price: number | null;
  status: string | null;
  url: string | null;
  score: number | null;
  monthly_cashflow: number | null;
  parcel_address: string | null;
  last_sale_price: number | null;
  last_sale_date: string | null;
}

export const api = {
  regions: () => request<{ regions: Region[]; supported_counties: Record<string, string> }>('/regions'),
  createRegion: (body: Omit<Region, 'id' | 'is_default'>) =>
    request<{ id: number }>('/regions', { method: 'POST', body: JSON.stringify(body) }),
  updateRegion: (id: number, body: Omit<Region, 'id' | 'is_default'>) =>
    request<{ id: number }>(`/regions/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteRegion: (id: number) => request<{ deleted: number }>(`/regions/${id}`, { method: 'DELETE' }),

  metrics: (geoIds: string[], metrics: string[], start?: string) =>
    request<{ series: Series[] }>(`/metrics${qs({ geo_ids: geoIds.join(','), metrics: metrics.join(','), start })}`),
  salesTrend: (zips: string[], maxPrice?: number) =>
    request<{ points: { period: string; median: number; count: number }[] }>(
      `/metrics/sales-trend${qs({ zips: zips.join(','), max_price: maxPrice })}`,
    ),


  listings: (params: { zips?: string; property_type?: string; garage_only?: boolean; status?: string; sort?: string; q?: string }) =>
    request<{ max_price: number; listings: Listing[] }>(`/listings${qs(params)}`),
  listing: (id: string) => request<ListingDetail>(`/listings/${encodeURIComponent(id)}`),
  rentEstimate: (id: string) =>
    request<{ rent: number }>(`/listings/${encodeURIComponent(id)}/rent-estimate`, { method: 'POST' }),

  sales: (params: { zips?: string; months?: number; under_cap?: boolean; property_class?: string; q?: string }) =>
    request<{ sales: Sale[] }>(`/sales${qs(params)}`),
  parcels: (params: { zips?: string; property_class?: string; address?: string; q?: string }) =>
    request<{ parcels: Parcel[] }>(`/parcels${qs(params)}`),
  sale: (id: number | string) => request<PropertyDetail>(`/sales/${encodeURIComponent(String(id))}`),
  parcel: (id: string) => request<PropertyDetail>(`/parcels/${encodeURIComponent(id)}`),

  syncStatus: () => request<SyncStatus>('/sync/status'),
  sync: (force = false) => request<{ started: boolean; message: string | null }>(`/sync${qs({ force })}`, { method: 'POST' }),

  settings: () => request<SettingsResponse>('/settings'),
  updateSettings: (values: Record<string, string>) =>
    request<SettingsResponse>('/settings', { method: 'PUT', body: JSON.stringify(values) }),

  watchlist: () => request<{ items: WatchItem[] }>('/watchlist'),
  addWatch: (body: { listing_id?: string; parcel_id?: string; notes?: string }) =>
    request<{ id: number }>('/watchlist', { method: 'POST', body: JSON.stringify(body) }),
  removeWatch: (id: number) => request<{ deleted: number }>(`/watchlist/${id}`, { method: 'DELETE' }),
};
