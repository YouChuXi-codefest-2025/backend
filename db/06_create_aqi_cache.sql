-- db/06_create_aqi_cache.sql
-- 以「10 分鐘時槽 + 位置 bucket」為唯一鍵，避免重複抓取
CREATE TABLE IF NOT EXISTS aqi_cache (
  id SERIAL PRIMARY KEY,
  slot_ts TIMESTAMPTZ NOT NULL,              -- 對齊到 10 分鐘邊界（以 UTC 存）
  lat DOUBLE PRECISION NOT NULL,             -- 原始查詢緯度
  lon DOUBLE PRECISION NOT NULL,             -- 原始查詢經度
  lat_bucket NUMERIC(10,3) NOT NULL,         -- 位置 bucket（四捨五入到 0.001 度 ≈ 110m）
  lon_bucket NUMERIC(10,3) NOT NULL,
  grid_lat DOUBLE PRECISION,                 -- CAMS 對應格點座標
  grid_lon DOUBLE PRECISION,
  pm25_ugm3 DOUBLE PRECISION NOT NULL,       -- µg/m³
  aqi INTEGER NOT NULL,
  aqi_category TEXT,
  cams_reference_time TEXT,                  -- 例如 "2025-11-09 12:00 UTC"
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 位置 + 時間 的唯一性（避免重複 insert 同一時槽與同一位置 bucket）
CREATE UNIQUE INDEX IF NOT EXISTS uq_aqi_slot_bucket
  ON aqi_cache (slot_ts, lat_bucket, lon_bucket);

-- 常用查詢索引（依時間新→舊）
CREATE INDEX IF NOT EXISTS idx_aqi_slot_ts_desc
  ON aqi_cache (slot_ts DESC);

-- 以地理鄰近查詢（若未來要找鄰近點）
-- 可選：若你想用 PostGIS，另建 geometry(Point,4326) + GIST 索引
