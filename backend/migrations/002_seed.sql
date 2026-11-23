INSERT INTO regions (id, name, is_default) VALUES (1, 'Easton', 1), (2, 'Bethlehem', 1);

INSERT INTO region_zips (region_id, zip) VALUES
  (1, '18040'), (1, '18042'), (1, '18045'),
  (2, '18015'), (2, '18017'), (2, '18018'), (2, '18020');

-- Bethlehem straddles both counties.
INSERT INTO region_counties (region_id, county_fips) VALUES
  (1, '42095'),
  (2, '42095'), (2, '42077');

INSERT INTO settings (key, value) VALUES
  ('max_price', '250000'),
  ('min_price', '0'),
  ('down_payment_pct', '25'),
  ('interest_rate_pct', ''),          -- blank = latest FRED 30-year rate + investor premium
  ('investor_rate_premium_pct', '0.75'),
  ('loan_years', '30'),
  ('closing_cost_pct', '3'),
  ('vacancy_pct', '8'),
  ('maintenance_pct', '8'),
  ('capex_pct', '8'),
  ('management_pct', '0'),
  ('insurance_annual', '1500'),
  ('fallback_tax_rate_pct', '2.2');   -- used when county millage is unknown
