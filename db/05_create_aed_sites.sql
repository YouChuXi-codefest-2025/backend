CREATE TABLE IF NOT EXISTS aed_sites (
  id SERIAL PRIMARY KEY,
  name TEXT,
  address TEXT,
  area_code TEXT,
  lat DOUBLE PRECISION,
  lon DOUBLE PRECISION,
  category TEXT,
  type TEXT,
  place TEXT,
  description TEXT,
  geom geometry(Point, 4326)
);

CREATE INDEX IF NOT EXISTS idx_aed_geom ON aed_sites USING GIST (geom);
