#!/usr/bin/env bash
# scripts/import.sh
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

# 來源座標系（TWD97）：3826=TM2(121E)；若不是可在 .env 設 SRC_SRID=3825/3827/3824
SRC_SRID="${SRC_SRID:-3826}"
# DBF 編碼：若你的 .dbf 是 BIG5，改成 BIG5
SHP_ENCODING="${SHP_ENCODING:-UTF-8}"

# --- 取得 SHP 路徑與圖層名 ---
# 用法：bash scripts/import.sh [path/to/your.shp]
SHP_PATH="${1:-}"
if [ -z "${SHP_PATH}" ]; then
  # 預設抓 data 底下唯一的 .shp
  matches=(data/district/*.shp)
  if [ "${#matches[@]}" -ne 1 ]; then
    echo "請指定 SHP 路徑：bash scripts/import.sh data/your.shp"
    exit 1
  fi
  SHP_PATH="${matches[0]}"
fi
if [ ! -f "${SHP_PATH}" ]; then
  echo "找不到檔案：${SHP_PATH}"
  exit 1
fi

SHP_BASENAME="$(basename "${SHP_PATH}")"
LAYER_NAME="${SHP_BASENAME%.shp}"

echo "===> 匯入目標：${SHP_PATH} (layer='${LAYER_NAME}')"
echo "===> 來源 SRID=${SRC_SRID}，DBF 編碼=${SHP_ENCODING}"

# --- 確認 gdal 容器存在（compose 服務名：tp-gdal），若未啟動則嘗試啟動 ---
if ! docker ps --format '{{.Names}}' | grep -q '^tp-gdal$'; then
  echo "未偵測到 tp-gdal；嘗試以 docker compose 啟動 gdal 服務..."
  if command -v docker compose >/dev/null 2>&1; then
    docker compose up -d gdal
  else
    echo "找不到 'docker compose' 指令，請先啟動 gdal 容器或自行執行："
    echo "  docker run -d --name tp-gdal --rm -v \"\$PWD/data\":/data:ro osgeo/gdal:alpine-small-latest sleep infinity"
    exit 1
  fi
fi

# --- 匯入（TWD97→WGS84），欄位映射：PNAME->city_name, TNAME->district_name ---
# 注意：如果你的 SHP 屬性不是 PNAME/TNAME，請改 SQL 這兩個欄位名。
echo "===> 以 ogr2ogr 匯入到 PostGIS (轉成 EPSG:4326, MultiPolygon)"
docker exec -i tp-gdal ogr2ogr -f "PostgreSQL" \
  PG:"host=${DB_HOST} dbname=${POSTGRES_DB} user=${POSTGRES_USER} password=${POSTGRES_PASSWORD} port=${DB_PORT}" \
  "/data/district/${SHP_BASENAME}" \
  -nln taipei_districts \
  -nlt MULTIPOLYGON \
  -lco GEOMETRY_NAME=geom \
  -overwrite \
  --config SHAPE_ENCODING "${SHP_ENCODING}" \
  -s_srs "EPSG:${SRC_SRID}" \
  -t_srs "EPSG:4326" \
  -sql "SELECT PNAME AS city_name, TNAME AS district_name, * FROM ${LAYER_NAME}"

# --- 建索引 + 分析 + 檢查 ---
echo "===> 建立 GIST 索引與 ANALYZE"
docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -c \
"CREATE INDEX IF NOT EXISTS idx_taipei_geom ON taipei_districts USING GIST (geom);
 ANALYZE taipei_districts;"

echo "===> 檢查筆數與 SRID"
docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c \
"SELECT count(*) AS rows, ST_SRID(geom) AS srid FROM taipei_districts GROUP BY ST_SRID(geom);"

echo "===> 取前幾筆看看"
docker exec -i tp-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c \
"SELECT city_name, district_name, ROUND((ST_Area(geom::geography)/1e6)::numeric,2) AS area_km2
 FROM taipei_districts ORDER BY district_name LIMIT 5;"

echo "✅ 匯入完成！"
