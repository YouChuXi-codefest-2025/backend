-- db/03_create_cooling_sites.sql

-- 正式表：市民納涼地點（或公共設施）清單
CREATE TABLE IF NOT EXISTS cooling_sites (
  id               SERIAL PRIMARY KEY,
  location_type    TEXT,            -- 設施地點（戶外或室內）
  name             TEXT,            -- 名稱
  district_name    TEXT,            -- 行政區
  address          TEXT,            -- 地址
  lon              DOUBLE PRECISION, -- 經度
  lat              DOUBLE PRECISION, -- 緯度
  phone            TEXT,            -- 市話
  ext              TEXT,            -- 分機
  mobile           TEXT,            -- 手機
  other_contact    TEXT,            -- 其他聯絡方式
  open_hours       TEXT,            -- 開放時間
  fan              BOOLEAN,         -- 電風扇 (Y/N)
  ac               BOOLEAN,         -- 冷氣 (Y/N)
  toilet           BOOLEAN,         -- 廁所 (Y/N)
  seating          BOOLEAN,         -- 座位 (Y/N)
  drinking         BOOLEAN,         -- 飲水設施 (Y/N)
  accessible_seat  BOOLEAN,         -- 無障礙座位 (Y/N)
  features         TEXT,            -- 其他特色及亮點
  notes            TEXT,            -- 備註
  geom             geometry(Point, 4326) -- 由 (lon,lat) 建立
);

-- 常用索引
CREATE INDEX IF NOT EXISTS idx_cooling_sites_geom ON cooling_sites USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_cooling_sites_district ON cooling_sites (district_name);