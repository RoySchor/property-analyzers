-- Backfill the match key on county sales from their parcel.
UPDATE sales SET address_norm = (SELECT p.address_norm FROM parcels p WHERE p.parcel_id = sales.parcel_id)
WHERE source = 'county' AND parcel_id IS NOT NULL;
