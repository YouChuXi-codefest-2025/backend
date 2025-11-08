#!/usr/bin/env bash
# scripts/import_aed.sh
set -euo pipefail

# --- 讀取環境變數 ---
if [ -f ".env" ]; then
  # shellcheck disable=SC1091
  source .env
fi
POSTGRES_DB="${POSTGRES_DB:-taipei}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"

# CSV 編碼：若來源是 BIG5，設 SHP_ENCODING=BIG5（沿用命名以保持一致）
CSV_ENCODING="${SHP_ENCODING:-UTF-8}"

# --- 取得 CSV 路徑 ---
# 用法：bash scripts/import_aed.sh [path/to/aed.csv]
CSV_PATH="${1:-}"
if [ -z "${CSV_PATH}" ]; then
  # 預設抓 data/aed 下唯一的 .csv
  matches=(data/aed/*.csv)
  if [ "${#matches[@]}" -ne 1 ]; then
    echo "請指定 CSV 路徑：bash scripts/import_aed.sh data/aed/taipei.csv"
    exit 1
  fi
  CSV_PATH="${matches[0]}"
fi
if [ ! -f "${CSV_PATH}" ]; then
  echo "找不到檔案：${CSV_PATH}"
  exit 1
fi

CSV_BASENAME="$(basename "${CSV_PATH}")"
echo "===> 匯入目標：${CSV_PATH} (base='${CSV_BASENAME}')"
echo "===> CSV 編碼=${CSV_ENCODING}"

# --- 確認 PostGIS 容器存在（compose 服務名：tp-postgis），若未啟動則嘗試啟動 ---
if ! docker ps --format '{{.Names}}' | grep -q '^tp-postgis$'; then
  echo "未偵測到 tp-postgis；嘗試以 docker compose 啟動 db 服務..."
  if command -v docker compose >/dev/null 2>&1; then
    docker compose up -d db
  else
    echo "找不到 'docker compose' 指令，請先啟動資料庫容器或自行執行："
    echo "  docker run -d --name tp-postgis -e POSTGRES_PASSWORD=${POSTGRES_PASSWORD} postgis/postgis:15-3.4"
    exit 1
  fi
fi

# # --- 建立 aed_sites 表結構（對應 db/05_create_aed_sites.sql）---
# echo "===> 建立/確認資料表結構 (db/05_create_aed_sites.sql)"
# docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
#   -f db/05_create_aed_sites.sql

# --- 匯入流程：建立暫存表(中文欄位) -> COPY -> 轉入正式表 -> 建 geom ---
echo "===> 準備暫存表（中文欄位; 全 TEXT）"
docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 <<'SQL'
DROP TABLE IF EXISTS aed_sites_raw;
CREATE TABLE aed_sites_raw (
  "場所名稱" TEXT,
  "場所地址" TEXT,
  "區域代碼" TEXT,
  "緯度" TEXT,
  "經度" TEXT,
  "場所分類" TEXT,
  "場所類型" TEXT,
  "AED放置地點" TEXT,
  "AED地點描述" TEXT
);
SQL

echo "===> 以 COPY 匯入 CSV（HEADER, ${CSV_ENCODING}）"
if [ "${CSV_ENCODING}" != "UTF-8" ]; then
  # 轉編碼 → UTF-8 後以 STDIN COPY
  iconv -f "${CSV_ENCODING}" -t UTF-8 "${CSV_PATH}" | dos2unix 2>/dev/null | \
    docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -c \
    "COPY aed_sites_raw FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');"
else
  # 直接把檔案拷進容器做 COPY（速度較快）
  docker cp "${CSV_PATH}" tp-postgis:/tmp/aed.csv
  docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -c \
    "COPY aed_sites_raw FROM '/tmp/aed.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');"
  docker exec -i tp-postgis rm -f /tmp/aed.csv
fi

echo "===> 原始暫存表筆數（aed_sites_raw）"
docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c \
"SELECT COUNT(*) AS raw_rows FROM aed_sites_raw;"

echo "===> 清空正式表 & 寫入（轉欄位 + 建立 geom）"
docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 <<'SQL'
TRUNCATE TABLE aed_sites RESTART IDENTITY;

INSERT INTO aed_sites (
  name, address, area_code, lat, lon, category, type, place, description, geom
)
SELECT
  NULLIF("場所名稱",'') AS name,
  NULLIF("場所地址",'') AS address,
  NULLIF("區域代碼",'') AS area_code,
  NULLIF("緯度",'')::double precision AS lat,
  NULLIF("經度",'')::double precision AS lon,
  NULLIF("場所分類",'') AS category,
  NULLIF("場所類型",'') AS type,
  NULLIF("AED放置地點",'') AS place,
  NULLIF("AED地點描述",'') AS description,
  CASE
    WHEN NULLIF("經度",'') IS NOT NULL AND NULLIF("緯度",'') IS NOT NULL
      THEN ST_SetSRID(ST_Point(NULLIF("經度",'')::double precision, NULLIF("緯度",'')::double precision), 4326)
    ELSE NULL
  END AS geom
FROM aed_sites_raw;

ANALYZE aed_sites;
DROP TABLE IF EXISTS aed_sites_raw;
SQL

# --- 建索引 + 分析 + 檢查 ---
echo "===> 建立 GIST 索引與 ANALYZE"
docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -c \
"CREATE INDEX IF NOT EXISTS idx_aed_geom ON aed_sites USING GIST (geom);
 ANALYZE aed_sites;"

echo "===> 檢查筆數與 SRID"
docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c \
"SELECT count(*) AS rows, ST_SRID(geom) AS srid FROM aed_sites GROUP BY ST_SRID(geom);"

echo "===> 取前幾筆看看（英文字段，一致於資料表定義）"
docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c \
"SELECT id, name, address, area_code, lon, lat, category, type, place, description, ST_AsText(geom) AS wkt
 FROM aed_sites
 WHERE geom IS NOT NULL
 ORDER BY id
 LIMIT 5;"

echo "✅ AED 匯入完成！"
