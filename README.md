# Property Analyzer

A local web app for researching investment properties in the Lehigh Valley, PA. It pulls free public real-estate data into one place and refreshes it every time it starts.

## Data sources

County assessment records ([Northampton](https://gis.northamptoncounty.org/arcgisweb/rest/services/Assessment_Services/Land_Records_LGM/MapServer), [Lehigh](https://services1.arcgis.com/XWDNR4PQlDQwrRCL/ArcGIS/rest/services/ATestParcel/FeatureServer)), [Zillow Research](https://www.zillow.com/research/data/), [Realtor.com Research](https://www.realtor.com/research/data/), [FRED](https://fred.stlouisfed.org/series/MORTGAGE30US), [Census ACS](https://www.census.gov/data/developers.html), [HUD Fair Market Rents](https://www.huduser.gov/portal/dataset/fmr-api.html), [HomeHarvest](https://github.com/ZacharyHampton/HomeHarvest) and [RentCast](https://developers.rentcast.io/).

## Getting started

Requires Python 3.13 and Node 22.

```bash
make setup   # install dependencies and create the database
make dev     # open http://localhost:5174
```

Optional API keys (Census, HUD, RentCast) go in `.env` — see `.env.example`.

## Stack

FastAPI · SQLite · React · TypeScript · Tailwind
