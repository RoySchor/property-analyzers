-- Regions you follow. A region is a named set of ZIPs plus the counties whose parcel data applies.
CREATE TABLE regions (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  is_default  INTEGER NOT NULL DEFAULT 0,
  is_active   INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE region_zips (
  region_id INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
  zip       TEXT NOT NULL,
  PRIMARY KEY (region_id, zip)
);

-- County parcel adapters to run for a region (42095 Northampton, 42077 Lehigh).
CREATE TABLE region_counties (
  region_id   INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
  county_fips TEXT NOT NULL,
  PRIMARY KEY (region_id, county_fips)
);

-- One row per data source; drives resync-on-launch and the status page.
CREATE TABLE source_sync (
  source          TEXT PRIMARY KEY,
  last_attempt_at TEXT,
  last_success_at TEXT,
  status          TEXT,            -- running | ok | skipped_unchanged | skipped_fresh | needs_key | error
  message         TEXT,            -- human-readable; never contains secrets
  etag            TEXT,
  last_modified   TEXT,
  scope_key       TEXT,            -- hash of tracked ZIPs/counties; a change forces a reload
  rows_upserted   INTEGER
);

-- Long-format time series from every market source.
CREATE TABLE market_metrics (
  source   TEXT NOT NULL,
  geo_type TEXT NOT NULL,          -- zip | metro | national
  geo_id   TEXT NOT NULL,
  metric   TEXT NOT NULL,
  period   TEXT NOT NULL,          -- YYYY-MM-DD
  value    REAL NOT NULL,
  PRIMARY KEY (source, geo_type, geo_id, metric, period)
);
CREATE INDEX idx_metrics_lookup ON market_metrics (geo_type, geo_id, metric, period);

CREATE TABLE area_scores (
  zip                    TEXT NOT NULL,
  computed_at            TEXT NOT NULL,
  zhvi                   REAL,
  zori                   REAL,
  gross_yield            REAL,
  price_growth_1y        REAL,
  price_growth_5y        REAL,
  rent_growth_1y         REAL,
  days_on_market         REAL,
  under_cap_listings     INTEGER,
  under_cap_share        REAL,
  under_cap_median_price REAL,
  investor_share         REAL,
  sales_12m              INTEGER,
  score                  REAL NOT NULL,
  PRIMARY KEY (zip, computed_at)
);

-- Current state of each county parcel.
CREATE TABLE parcels (
  parcel_id      TEXT PRIMARY KEY,  -- '<county_fips>:<county parcel id>'
  county_fips    TEXT NOT NULL,
  address        TEXT,
  address_norm   TEXT,
  zip            TEXT,
  muni           TEXT,
  land_use_code  TEXT,
  property_class TEXT,              -- single_family | multi_family | condo | garage | parking | land | commercial | other
  units          INTEGER,
  beds           INTEGER,
  baths          REAL,
  sqft           INTEGER,
  year_built     INTEGER,
  lat            REAL,
  lon            REAL,
  owner_name     TEXT,
  owner_mail     TEXT,
  is_homestead   INTEGER,
  is_absentee    INTEGER,
  assessed_value REAL,
  market_value   REAL,
  last_sale_price REAL,
  last_sale_date TEXT,
  last_sale_valid INTEGER,
  annual_tax_est REAL,
  updated_at     TEXT NOT NULL
);
CREATE INDEX idx_parcels_zip ON parcels (zip);
CREATE INDEX idx_parcels_addr ON parcels (address_norm);
CREATE INDEX idx_parcels_class ON parcels (property_class);

-- Append-only: a row is written only when the sale, assessment or owner changes.
CREATE TABLE parcel_snapshots (
  parcel_id      TEXT NOT NULL REFERENCES parcels(parcel_id),
  captured_at    TEXT NOT NULL,
  sale_price     REAL,
  sale_date      TEXT,
  sale_valid     INTEGER,
  assessed_value REAL,
  market_value   REAL,
  owner_name     TEXT,
  PRIMARY KEY (parcel_id, captured_at)
);

CREATE TABLE sales (
  id         INTEGER PRIMARY KEY,
  parcel_id  TEXT REFERENCES parcels(parcel_id),
  address    TEXT,
  zip        TEXT,
  sale_date  TEXT NOT NULL,
  sale_price REAL NOT NULL,
  is_valid   INTEGER NOT NULL DEFAULT 1,
  source     TEXT NOT NULL,          -- county | homeharvest
  UNIQUE (source, parcel_id, address, sale_date, sale_price)
);
CREATE INDEX idx_sales_zip_date ON sales (zip, sale_date);

CREATE TABLE tax_history (
  parcel_id      TEXT NOT NULL REFERENCES parcels(parcel_id),
  tax_year       INTEGER NOT NULL,
  assessed_value REAL,
  tax_amount     REAL,
  source         TEXT NOT NULL,
  PRIMARY KEY (parcel_id, tax_year, source)
);

CREATE TABLE listings (
  listing_id      TEXT PRIMARY KEY,   -- Realtor.com property_id
  parcel_id       TEXT REFERENCES parcels(parcel_id),
  match_method    TEXT,
  address         TEXT,
  address_norm    TEXT,
  city            TEXT,
  zip             TEXT,
  property_type   TEXT,
  has_garage      INTEGER,
  status          TEXT,
  list_price      REAL,
  list_date       TEXT,
  last_sold_price REAL,
  last_sold_date  TEXT,
  estimated_value REAL,
  beds            INTEGER,
  baths           REAL,
  sqft            INTEGER,
  year_built      INTEGER,
  lot_sqft        INTEGER,
  hoa_fee         REAL,
  lat             REAL,
  lon             REAL,
  url             TEXT,
  photo_url       TEXT,
  first_seen_at   TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL
);
CREATE INDEX idx_listings_zip_status ON listings (zip, status);

CREATE TABLE listing_snapshots (
  listing_id  TEXT NOT NULL REFERENCES listings(listing_id),
  captured_at TEXT NOT NULL,
  list_price  REAL,
  status      TEXT,
  PRIMARY KEY (listing_id, captured_at)
);

CREATE TABLE rent_estimates (
  listing_id TEXT NOT NULL REFERENCES listings(listing_id),
  source     TEXT NOT NULL,           -- rentcast | zori
  rent       REAL NOT NULL,
  value_est  REAL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (listing_id, source)
);

CREATE TABLE rentcast_usage (
  month TEXT PRIMARY KEY,             -- YYYY-MM
  calls INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE deal_scores (
  listing_id                 TEXT PRIMARY KEY REFERENCES listings(listing_id),
  computed_at                TEXT NOT NULL,
  prev_sale_price            REAL,
  prev_sale_date             TEXT,
  change_since_sale_pct      REAL,
  zip_change_same_period_pct REAL,
  annual_tax                 REAL,
  tax_source                 TEXT,    -- county_millage | estimate
  rent                       REAL,
  rent_source                TEXT,
  monthly_piti               REAL,
  monthly_cashflow           REAL,
  cap_rate                   REAL,
  cash_on_cash               REAL,
  price_per_sqft             REAL,
  comp_price_per_sqft        REAL,
  score                      REAL
);

CREATE TABLE distressed_sales (
  id          INTEGER PRIMARY KEY,
  county_fips TEXT NOT NULL,
  sale_type   TEXT NOT NULL,
  sale_date   TEXT,
  parcel_id   TEXT REFERENCES parcels(parcel_id),
  address     TEXT,
  upset_price REAL,
  source_url  TEXT,
  UNIQUE (county_fips, sale_type, sale_date, address)
);

CREATE TABLE watchlist (
  id         INTEGER PRIMARY KEY,
  listing_id TEXT REFERENCES listings(listing_id),
  parcel_id  TEXT REFERENCES parcels(parcel_id),
  notes      TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (listing_id IS NOT NULL OR parcel_id IS NOT NULL)
);

CREATE TABLE settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
