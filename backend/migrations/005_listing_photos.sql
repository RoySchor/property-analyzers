-- Up to 12 photo URLs per listing (JSON array, primary photo first).
ALTER TABLE listings ADD COLUMN photos TEXT;
