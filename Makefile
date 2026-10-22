SHELL := /bin/sh
COMPOSE ?= docker compose
API_URL ?= http://localhost:8000
BACKUP_DIR ?= backups
BACKUP_KEEP_DAYS ?= 14
RESTORE_DATE ?=
SERVICE ?= api

.DEFAULT_GOAL := help

.PHONY: help
help:
	@printf '%s\n' 'Hotspot deployment targets' '' \
	  '  make deploy              Build, migrate, and start all services' \
	  '  make deploy-code         Pull latest code, then deploy' \
	  '  make restart             Rebuild and recreate application services' \
	  '  make restart-service SERVICE=api' \
	  '  make stop                Stop services without deleting volumes' \
	  '  make ps                  Show service status' \
	  '  make health              Check API and database-backed summary' \
	  '  make logs                Follow service logs' \
	  '  make migrate             Apply database migrations' \
	  '  make backup              Dump hotspot and raster databases' \
	  '  make restore CONFIRM=YES RESTORE_DATE=YYYY-MM-DD'

.PHONY: build up up-service deploy deploy-code restart restart-service
build:
	$(COMPOSE) --profile service build

up:
	$(COMPOSE) up -d db api frontend

up-service:
	$(COMPOSE) --profile service up -d

deploy: build up migrate up-service health

deploy-code:
	git pull --ff-only
	$(MAKE) deploy

restart:
	$(COMPOSE) up -d --build --force-recreate api frontend
	$(MAKE) migrate
	$(COMPOSE) --profile service up -d --build --force-recreate worker-snpp-service worker-noaa20-service worker-aqua-service worker-tera-service modis-converter-aqua-service modis-converter-tera-service
	$(MAKE) health

restart-service:
	$(COMPOSE) --profile service up -d --build --force-recreate $(SERVICE)

.PHONY: stop ps logs logs-service health migrate
stop:
	$(COMPOSE) --profile service stop

ps:
	$(COMPOSE) --profile service ps

logs:
	$(COMPOSE) --profile service logs -f --tail=120

logs-service:
	$(COMPOSE) --profile service logs -f --tail=120 $(SERVICE)

health:
	curl -fsS $(API_URL)/api/v1/health
	@printf '\n'
	curl -fsS $(API_URL)/api/v1/summary > /dev/null

migrate:
	$(COMPOSE) run --rm worker hotspot db migrate

.PHONY: backup restore
backup:
	@set -eu; umask 077; mkdir -p "$(BACKUP_DIR)"; \
	  for database in hotspot raster; do \
	    tmp="$(BACKUP_DIR)/$$database.tmp"; trap 'rm -f "$$tmp"' EXIT; \
	    $(COMPOSE) exec -T db pg_dump -U hotspot -Fc "$$database" > "$$tmp"; \
	    $(COMPOSE) exec -T db pg_restore --list < "$$tmp" > /dev/null; \
	    mv "$$tmp" "$(BACKUP_DIR)/$$database-$$(date +%F).dump"; \
	  done; \
	  find "$(BACKUP_DIR)" -name '*.dump' -mtime +$(BACKUP_KEEP_DAYS) -delete

restore:
	@test "$(CONFIRM)" = "YES" && test -n "$(RESTORE_DATE)" && test -f "$(BACKUP_DIR)/hotspot-$(RESTORE_DATE).dump" && test -f "$(BACKUP_DIR)/raster-$(RESTORE_DATE).dump" || (printf '%s\n' 'Run: make restore CONFIRM=YES RESTORE_DATE=YYYY-MM-DD' && exit 1)
	$(COMPOSE) --profile service stop
	$(COMPOSE) up -d db
	$(COMPOSE) exec -T db pg_restore --list < "$(BACKUP_DIR)/hotspot-$(RESTORE_DATE).dump" > /dev/null
	$(COMPOSE) exec -T db pg_restore --list < "$(BACKUP_DIR)/raster-$(RESTORE_DATE).dump" > /dev/null
	@set -e; for database in hotspot raster; do \
	  $(COMPOSE) exec -T db dropdb -U hotspot --if-exists "$$database"; \
	  $(COMPOSE) exec -T db createdb -U hotspot "$$database"; \
	  $(COMPOSE) exec -T db pg_restore -U hotspot -d "$$database" --no-owner --exit-on-error < "$(BACKUP_DIR)/$$database-$(RESTORE_DATE).dump"; \
	done
	$(MAKE) up
	$(MAKE) up-service
	$(MAKE) health
