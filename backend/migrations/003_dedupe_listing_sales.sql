-- SQLite treats NULLs as distinct in UNIQUE constraints, so sold records without a parcel duplicated on every sync.
DELETE FROM sales WHERE parcel_id IS NULL AND id NOT IN (
  SELECT MIN(id) FROM sales WHERE parcel_id IS NULL GROUP BY source, address, zip, substr(sale_date, 1, 10), sale_price
);
UPDATE sales SET sale_date = substr(sale_date, 1, 10) WHERE length(sale_date) > 10;
UPDATE listings SET list_date = substr(list_date, 1, 10) WHERE length(list_date) > 10;
UPDATE listings SET last_sold_date = substr(last_sold_date, 1, 10) WHERE length(last_sold_date) > 10;
CREATE UNIQUE INDEX idx_sales_unparceled ON sales (source, address, zip, sale_date, sale_price) WHERE parcel_id IS NULL;
