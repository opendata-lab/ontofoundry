UV ?= uv
NPM ?= npm

.PHONY: install api-dev web-dev dataagent-up dataagent-down dataagent-build dataagent-test serve build test lint

install:
	cd apps/api && $(UV) sync --python 3.13 --locked
	$(NPM) ci

api-dev:
	cd apps/api && $(UV) run --python 3.13 uvicorn ontofoundry_api.main:app --host 127.0.0.1 --port 8000 --reload

web-dev:
	cd apps/web && $(NPM) run dev

dataagent-up:
	docker compose --env-file apps/api/.env up -d --build dataagent-backend

dataagent-down:
	docker compose stop dataagent-backend dataagent-redis

dataagent-build:
	cd dataagent/dataagent-runtime-pi && $(NPM) ci && $(NPM) run build

dataagent-test:
	cd dataagent/dataagent-runtime-pi && $(NPM) test
	cd dataagent/dataagent-backend && $(UV) run --python 3.13 --with-requirements requirements.txt pytest -q

build:
	$(NPM) run build -w @opendataworks/dataagent-runtime-pi
	cd apps/web && $(NPM) run build

serve:
	cd apps/api && ONTOFOUNDRY_WEB_DIST=../web/dist $(UV) run --python 3.13 uvicorn ontofoundry_api.main:app --host 127.0.0.1 --port 8000

test:
	cd apps/api && $(UV) run --python 3.13 pytest -q
	cd dataagent/dataagent-backend && $(UV) run --python 3.13 --with-requirements requirements.txt pytest -q
	$(NPM) test -w @opendataworks/dataagent-runtime-pi
	cd apps/web && $(NPM) test -- --run

lint:
	cd apps/api && $(UV) run --python 3.13 ruff check src tests
	$(NPM) run typecheck -w @opendataworks/dataagent-runtime-pi
	cd apps/web && $(NPM) run lint
