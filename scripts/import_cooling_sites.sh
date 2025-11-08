#!/usr/bin/env bash
# scripts/import_csv.sh
set -euo pipefail

# 讀取 .env
if [ -f ".env" ]; then
  # shellcheck disable=SC1091
  source .env
fi

POSTGRES_DB="${POSTGRES_DB:-taipei}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"

CSV_PATH="${1:-data/cooling_sites/taipei.csv}"          # 可傳入自訂路徑
CSV_ENCODING="${CSV_ENCODING:-UTF-8}"     # 若來源是 BIG5：export CSV_ENCODING=BIG5
PSQL="docker exec -i tp-postgis psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -v ON_ERROR_STOP=1"

if [ ! -f "${CSV_PATH}" ]; then
  echo "找不到 CSV：${CSV_PATH}"
  exit 1
fi

# echo "===> 建立正式表（若尚未建立）"
# $PSQL -f db/03_create_cooling_sites.sql

echo "===> 準備暫存表（中文欄位; 全 TEXT）"
$PSQL <<'SQL'
DROP TABLE IF EXISTS cooling_sites_raw;
CREATE TABLE cooling_sites_raw (
  "編號" TEXT,
  "設施地點（戶外或室內）" TEXT,
  "名稱" TEXT,
  "行政區" TEXT,
  "地址" TEXT,
  "經度" TEXT,
  "緯度" TEXT,
  "市話" TEXT,
  "分機" TEXT,
  "手機" TEXT,
  "其他聯絡方式" TEXT,
  "開放時間" TEXT,
  "電風扇" TEXT,
  "冷氣" TEXT,
  "廁所" TEXT,
  "座位" TEXT,
  "飲水設施（例如：飲水機；直飲台；奉茶點等）" TEXT,
  "無障礙座位" TEXT,
  "其他特色及亮點" TEXT,
  "備註" TEXT
);
SQL

echo "===> 以 COPY 匯入 CSV（HEADER, ${CSV_ENCODING}）"
if [ "${CSV_ENCODING}" != "UTF-8" ]; then
  iconv -f "${CSV_ENCODING}" -t UTF-8 "${CSV_PATH}" | dos2unix | \
    docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c \
    "COPY cooling_sites_raw FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');"
else
  dos2unix "${CSV_PATH}" 2>/dev/null || true
  docker cp "${CSV_PATH}" tp-postgis:/tmp/taipei.csv
  docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c \
    "COPY cooling_sites_raw FROM '/tmp/taipei.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');"
  docker exec -i tp-postgis rm -f /tmp/taipei.csv
fi

echo "===> 原始暫存表筆數（cooling_sites_raw）"
$PSQL -c "SELECT COUNT(*) AS raw_rows FROM cooling_sites_raw;"

echo "===> 轉入正式表（清空後重灌；必要時改成 UPSERT）"
$PSQL <<'SQL'
TRUNCATE TABLE cooling_sites;

INSERT INTO cooling_sites (
  location_type, name, district_name, address, lon, lat,
  phone, ext, mobile, other_contact, open_hours,
  fan, ac, toilet, seating, drinking, accessible_seat,
  features, notes, geom
)
SELECT
  NULLIF("設施地點（戶外或室內）", '') AS location_type,
  NULLIF("名稱", '') AS name,
  NULLIF("行政區", '') AS district_name,
  NULLIF("地址", '') AS address,
  NULLIF("經度", '')::double precision AS lon,
  NULLIF("緯度", '')::double precision AS lat,
  NULLIF("市話", '') AS phone,
  NULLIF("分機", '') AS ext,
  NULLIF("手機", '') AS mobile,
  NULLIF("其他聯絡方式", '') AS other_contact,
  NULLIF("開放時間", '') AS open_hours,
  CASE WHEN upper(coalesce("電風扇", '')) = 'Y' THEN true ELSE false END AS fan,
  CASE WHEN upper(coalesce("冷氣", '')) = 'Y' THEN true ELSE false END AS ac,
  CASE WHEN upper(coalesce("廁所", '')) = 'Y' THEN true ELSE false END AS toilet,
  CASE WHEN upper(coalesce("座位", '')) = 'Y' THEN true ELSE false END AS seating,
  CASE WHEN upper(coalesce("飲水設施（例如：飲水機；直飲台；奉茶點等）", '')) = 'Y' THEN true ELSE false END AS drinking,
  CASE WHEN upper(coalesce("無障礙座位", '')) = 'Y' THEN true ELSE false END AS accessible_seat,
  NULLIF("其他特色及亮點", '') AS features,
  NULLIF("備註", '') AS notes,
  CASE
    WHEN NULLIF("經度", '') IS NOT NULL AND NULLIF("緯度", '') IS NOT NULL
      THEN ST_SetSRID(ST_Point(NULLIF("經度",'')::double precision, NULLIF("緯度",'')::double precision), 4326)
    ELSE NULL
  END AS geom
FROM cooling_sites_raw;

ANALYZE cooling_sites;
SQL

echo "===> 正式表筆數（cooling_sites）"
$PSQL -c "SELECT COUNT(*) AS rows FROM cooling_sites;"

echo "===> 取前 5 筆（英文字段，與 .sql 一致）"
$PSQL -c "
SELECT
  id,
  location_type,
  name,
  district_name,
  address,
  lon,
  lat,
  phone,
  ext,
  mobile,
  other_contact,
  open_hours,
  fan,
  ac,
  toilet,
  seating,
  drinking,
  accessible_seat,
  features,
  notes,
  ST_AsText(geom) AS wkt
FROM cooling_sites
ORDER BY id
LIMIT 5;
"

echo "===> 清理暫存表"
$PSQL -c "DROP TABLE IF EXISTS cooling_sites_raw;"

echo "✅ 匯入完成並完成筆數檢查與前 5 筆列印！"
