UV ?= uv
NPM ?= npm

.PHONY: install api-dev web-dev dataagent-up dataagent-down dataagent-build dataagent-images dataagent-test serve build test lint

install:
	cd apps/api && $(UV) sync --python 3.13 --locked
	$(NPM) ci

api-dev:
	cd apps/api && $(UV) run --python 3.13 uvicorn ontofoundry_api.main:app --host 127.0.0.1 --port 8000 --reload

web-dev:
	cd apps/web && $(NPM) run dev

dataagent-up:
	docker compose --env-file apps/api/.env up -d --build of-backend of-runner of-frontend

dataagent-down:
	docker compose stop of-frontend of-runner of-backend dataagent-redis

dataagent-build:
	cd dataagent/dataagent-runtime-pi && $(NPM) ci && $(NPM) run build

dataagent-images:
	docker build -t of-backend:local --target backend -f apps/api/Dockerfile .
	docker build -t of-runner:local --target runner -f apps/api/Dockerfile .
	docker build -t of-frontend:local -f apps/web/Dockerfile .

dataagent-test:
	cd dataagent/dataagent-runtime-pi && $(NPM) test

build:
	$(NPM) run build -w @ontofoundry/agent-runtime-pi
	cd apps/web && $(NPM) run build

serve:
	cd apps/api && ONTOFOUNDRY_WEB_DIST=../web/dist $(UV) run --python 3.13 uvicorn ontofoundry_api.main:app --host 127.0.0.1 --port 8000

test:
	cd apps/api && $(UV) run --python 3.13 pytest -q
	$(NPM) test -w @ontofoundry/agent-runtime-pi
	cd apps/web && $(NPM) test -- --run

lint:
	cd apps/api && $(UV) run --python 3.13 ruff check src tests
	$(NPM) run typecheck -w @ontofoundry/agent-runtime-pi
	cd apps/web && $(NPM) run lint
