# =========
# Makefile
# =========
SHELL := /bin/bash

# 讀 .env（若存在），並導出成環境變數讓 docker exec 使用
ifneq (,$(wildcard .env))
include .env
export
endif

# 可調參數（必要時覆寫：make import-shp SHP=data/xxx.shp SRC_SRID=3825）
COMPOSE := docker compose
PSQL    := docker exec -i tp-postgis psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v ON_ERROR_STOP=1

# 預設檔案路徑
SHP        ?=        # 預設留空，scripts/import.sh 會自動抓 data/*.shp（唯一時）
CSV        ?= data/cooling_sites/taipei.csv
CSV_ENCODING ?= UTF-8

# 幫助
.PHONY: help
help:
	@echo "用法：make <target>"
	@echo
	@echo "核心流程："
	@echo "  make up          # 啟動 db + gdal + web"
	@echo "  make init-db     # 套用 SQL（01/02/03）初始化資料表"
	@echo "  make import-shp  # 匯入 TWD97 SHP（自動轉 4326，多邊形）"
	@echo "  make import-csv  # 匯入 taipei.csv（轉欄位/布林/建立 POINT geom）"
	@echo "  make seed        # = init-db + import-shp + import-csv"
	@echo "  make health      # 檢查 /health 與列 5 筆 cooling_sites"
	@echo
	@echo "其他常用："
	@echo "  make up-db / up-gdal / up-web"
	@echo "  make build       # 重建 web 映像"
	@echo "  make logs        # 追 web logs"
	@echo "  make db-psql     # 進入 psql"
	@echo "  make web-sh      # 進入 web 容器 shell"
	@echo "  make down        # 停止不刪 volume"
	@echo "  make clean       # 停止並刪除 volume（資料會被清空！）"

# --- 啟動服務 ---
.PHONY: up up-db up-gdal up-web build restart logs ps
up: up-db up-gdal up-web
	@echo "All services are up."

up-db:
	$(COMPOSE) up -d db

up-gdal:
	$(COMPOSE) up -d gdal

up-web: build
	$(COMPOSE) up -d web

build:
	$(COMPOSE) build web

restart:
	$(COMPOSE) restart web

logs:
	$(COMPOSE) logs -f web

ps:
	$(COMPOSE) ps

# --- 初始化資料庫（套用 SQL 檔） ---
.PHONY: init-db
init-db: up-db
	@echo "Apply SQL: 01_enable_postgis.sql"
	$(PSQL) -f db/01_enable_postgis.sql
	@echo "Apply SQL: 02_init_empty_table.sql"
	$(PSQL) -f db/02_init_empty_table.sql
	@echo "Apply SQL: 03_create_cooling_sites.sql"
	$(PSQL) -f db/03_create_cooling_sites.sql

# --- 匯入 SHP（使用 scripts/import.sh） ---
.PHONY: import-shp
import-shp: up-gdal up-db
	@echo "Importing SHP via scripts/import_shp_twd97.sh (SHP='$(SHP)')"
	@# 允許 SHP 省略（data/ 只有一個 .shp 時自動偵測）
	@if [ -n "$(SHP)" ]; then bash scripts/import_shp_twd97.sh "$(SHP)"; else bash scripts/import_shp_twd97.sh; fi

# --- 匯入 CSV（使用 scripts/import_csv.sh） ---
.PHONY: import-csv
import-csv: up-db
	@echo "Importing CSV via scripts/import_cooling_sites.sh (CSV='$(CSV)', CSV_ENCODING='$(CSV_ENCODING)')"
	@CSV_ENCODING='$(CSV_ENCODING)' bash scripts/import_cooling_sites.sh '$(CSV)'

# --- 一次完成（初始化 + 匯入 SHP/CSV） ---
.PHONY: seed
seed: import-shp import-csv
	@echo "Seed done."

# --- 健康檢查與簡單驗證 ---
.PHONY: health
health: up-web
	@echo "Check Flask /health"
	@curl -s http://localhost:5000/health | jq .
	@echo "List 5 cooling sites (id, name, district_name)"
	@$(PSQL) -c "SELECT id, name, district_name FROM cooling_sites ORDER BY id LIMIT 5;"
	@echo "Try endpoints:"
	@echo "  GET /sites?limit=5"
	@curl -s "http://localhost:5000/sites?limit=5" | jq '.items | .[0:3]'
	@echo "  GET /sites/nearest?lat=25.033964&lon=121.564468"
	@curl -s "http://localhost:5000/sites/nearest?lat=25.033964&lon=121.564468" | jq .

# --- 便利工具 ---
.PHONY: db-psql web-sh db-sh
db-psql: up-db
	docker exec -it tp-postgis psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

web-sh: up-web
	docker exec -it tp-flask sh

db-sh: up-db
	docker exec -it tp-postgis bash

# --- 關閉 / 清理 ---
.PHONY: down clean
down:
	$(COMPOSE) down

clean:
	$(COMPOSE) down -v
