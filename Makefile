UV ?= uv
NPM ?= npm

.PHONY: install api-dev web-dev compose-up compose-down serve build test lint

install:
	cd apps/api && $(UV) sync --python 3.13 --locked
	$(NPM) ci

api-dev:
	cd apps/api && $(UV) run --python 3.13 uvicorn ontofoundry_api.main:app --host 127.0.0.1 --port 8000 --reload

web-dev:
	cd apps/web && $(NPM) run dev

compose-up:
	docker compose --env-file apps/api/.env up -d --build of-backend of-frontend

compose-down:
	docker compose stop of-frontend of-backend




build:
	cd apps/web && $(NPM) run build

serve:
	cd apps/api && ONTOFOUNDRY_WEB_DIST=../web/dist $(UV) run --python 3.13 uvicorn ontofoundry_api.main:app --host 127.0.0.1 --port 8000

test:
	cd apps/api && $(UV) run --python 3.13 pytest -q
	cd apps/web && $(NPM) test -- --run

lint:
	cd apps/api && $(UV) run --python 3.13 ruff check src tests
	cd apps/web && $(NPM) run lint
