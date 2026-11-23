-- Metro-wide / national aggregates and ZIP area rankings are no longer used.
DELETE FROM market_metrics WHERE geo_type IN ('metro', 'national') AND metric != 'mortgage_30y';
DELETE FROM source_sync WHERE source IN ('zillow_zhvi_metro', 'zillow_zori_metro', 'realtor_metro');
DROP TABLE IF EXISTS area_scores;
