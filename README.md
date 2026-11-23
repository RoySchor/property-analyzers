# Property Analyzer

A local web app for researching small residential investment properties in Pennsylvania's Lehigh Valley (Easton and Bethlehem by default). It combines free public data — county assessment records, Zillow and Realtor.com research data, Census and HUD statistics, and live listings — into one place, and re-syncs automatically every time it starts.

**Use it to:** follow long-term price and rent trends by ZIP, see a property's full sale and tax history, check whether an asking price is above or below what the neighborhood has done since the last sale, and run cash-flow math on every listing under a price cap.

## Features

- **Trends by ZIP:** home values and rents back to 2000, inventory, days on market, vacancy, renter share and the 30-year mortgage rate.
- **Listings** under a configurable price cap (default $250k), each with:
  - previous sale price and date, the markup since, and how much the ZIP moved over the same period
  - real property tax from county assessments × current millage
  - estimated rent, monthly cash flow and cash-on-cash return, using adjustable assumptions
  - photos, comparable sales and links to Realtor.com, Zillow, Google Maps and the county record
- **Sales:** recent arm's-length sales from county records, with buyer type (owner-occupant vs. likely investor) and a detail page per sale.
- **Garages & parking:** stand-alone garage and parking parcels (rarely on listing sites) plus listings with garages.
- **Configurable areas:** add any ZIPs; county parcel data is supported for Northampton and Lehigh counties.
- **Search, sort and filter** on every table, including a price slider.

Mobile homes and vacant land are excluded by design.

## Data sources

| Source | Provides | Key |
|---|---|---|
| [Northampton County GIS](https://gis.northamptoncounty.org/arcgisweb/rest/services/Assessment_Services/Land_Records_LGM/MapServer) and [Lehigh County GIS](https://services1.arcgis.com/XWDNR4PQlDQwrRCL/ArcGIS/rest/services/ATestParcel/FeatureServer) | Every parcel: last sale, assessed value, land use, owner, beds/baths/sqft | — |
| [Northampton millage rates](https://www.ncpub.org/_web/content/pdffiles/Millage%20rates%20as%20of%20January%201%202026.pdf) | Tax rates per municipality (`config/millage.json`) | — |
| [Zillow Research](https://www.zillow.com/research/data/) | Home value (ZHVI) and rent (ZORI) indexes by ZIP | — |
| [Realtor.com Research](https://www.realtor.com/research/data/) | Inventory, listing prices, days on market by ZIP | — |
| [FRED](https://fred.stlouisfed.org/series/MORTGAGE30US) | 30-year mortgage rate | — |
| [HomeHarvest](https://github.com/ZacharyHampton/HomeHarvest) (Realtor.com) | Active and recently sold listings, photos | — |
| [Census ACS](https://www.census.gov/data/developers.html) | Vacancy, renter share, income by ZIP | Free |
| [HUD Fair Market Rents](https://www.huduser.gov/portal/dataset/fmr-api.html) | Rent benchmarks by bedroom count | Free |
| [RentCast](https://developers.rentcast.io/) | On-demand rent estimate for a single property | Free tier |

County sources only publish each parcel's *latest* sale, so the app snapshots every parcel on each sync and builds sale history over time.

## Getting started

Requires Python 3.13 and Node 22.

```bash
make setup     # create venv, install dependencies, create the database
make dev       # backend at http://127.0.0.1:8001, app at http://localhost:5174
make test      # backend tests
```

Optional API keys go in `.env` (copied from `.env.example`). Sources without a key are skipped, not failed.

| Variable | Get one at |
|---|---|
| `CENSUS_API_KEY` | https://api.census.gov/data/key_signup.html |
| `HUD_API_TOKEN` | https://www.huduser.gov/hudapi/public/register |
| `RENTCAST_API_KEY` | https://app.rentcast.io/app/api (Developer plan: 50 free calls/month) |

The first sync takes a few minutes (≈225k parcels and an 838 MB Realtor.com file, streamed and filtered to tracked ZIPs). Later launches only refresh what has changed.

## How it works

```
Public sources ──► sync engine ──► SQLite ──► analysis ──► FastAPI ──► React
```

- **Sync** (`backend/services/sync_runner.py`) runs each source independently on startup or on demand. Sources are skipped when still fresh or when the remote file is unchanged (ETag / Last-Modified), and one failure never blocks the others.
- **History** (`sources/county.py`): a parcel snapshot is written only when its sale, assessment or owner changes.
- **Matching:** listings are linked to county parcels by normalized address, falling back to coordinates.
- **Deal math** (`services/deal_math.py`): mortgage at the current FRED rate plus an investor premium, county taxes, insurance, vacancy, maintenance, CapEx and management — all adjustable in Settings.
- **RentCast budget guard** (`services/rentcast.py`): at most 45 calls in any rolling 31-day window, recorded before each request under a file lock, so the free tier can't be exceeded.

## Project structure

```
backend/
  main.py              FastAPI app; starts a background sync on launch
  migrations/          numbered SQL migrations, applied on startup
  routers/             API endpoints
  services/            sync engine, source adapters, analysis, RentCast guard
config/millage.json    county tax rates
frontend/src/          React + TypeScript + Tailwind (pages, components)
tests/                 pytest suite
```

## Limitations

- Rent estimates fall back to HUD county-wide rents or Zillow ZIP rents when no property-specific estimate exists, so cash flow is approximate.
- Lehigh County millage isn't configured yet; taxes there use an estimated rate.
- Some land-use code meanings for Lehigh County are inferred from the data (no public code table).
- Listings come from a community scraper and may break if Realtor.com changes its site.

## Disclaimer

For personal research only; not financial advice. Data comes from public sources and may be incomplete or out of date — verify with the county and a licensed professional before acting. Respect each source's terms of use.
