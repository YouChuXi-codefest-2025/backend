-- 台北市行政區表
CREATE TABLE IF NOT EXISTS taipei_districts (
  id SERIAL PRIMARY KEY,
  city_name TEXT DEFAULT '臺北市',
  district_name TEXT NOT NULL,
  geom geometry(MultiPolygon, 4326) NOT NULL
);
-- 空間索引
CREATE INDEX IF NOT EXISTS idx_taipei_geom ON taipei_districts USING GIST (geom);


