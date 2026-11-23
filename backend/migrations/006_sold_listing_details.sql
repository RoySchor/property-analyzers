-- Keep the Realtor.com link, photos and a match key for sold records, so a sale's detail page can show them.
ALTER TABLE sales ADD COLUMN address_norm TEXT;
ALTER TABLE sales ADD COLUMN url TEXT;
ALTER TABLE sales ADD COLUMN photos TEXT;
CREATE INDEX idx_sales_parcel ON sales (parcel_id);
CREATE INDEX idx_sales_zip_norm ON sales (zip, address_norm);
