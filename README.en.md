<div align="center">

<img src="docs/assets/logo.svg" width="72" height="72" alt="OntoFoundry Logo" />

<h1>OntoFoundry</h1>

<p>
  <strong>Enterprise Ontology Engineering & Semantic Layer Platform</strong><br />
  Grounding business specifications, database schemas, and domain knowledge into one versioned, evidence-backed semantic layer for AI agents and applications
</p>

<p>
  <a href="https://github.com/opendata-lab/ontofoundry/actions/workflows/ci.yml"><img src="https://github.com/opendata-lab/ontofoundry/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/opendata-lab/ontofoundry/releases"><img src="https://img.shields.io/github/v/release/opendata-lab/ontofoundry?sort=semver&filter=v*&style=flat-square&color=0061ef" alt="Release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-156d3b?style=flat-square" alt="License Apache-2.0" /></a>
  <img src="https://img.shields.io/badge/MCP-2026--07--28-716096?style=flat-square" alt="MCP 2026-07-28" />
  <img src="https://img.shields.io/badge/Apache%20Ossie-0.2.0.dev0-94600b?style=flat-square" alt="Apache Ossie" />
</p>

<p>
  <a href="README.md">简体中文</a> · <strong>English</strong>
</p>

<p>
  <a href="#core-capabilities">Core Capabilities</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#ai--mcp-integration">AI & MCP Integration</a> ·
  <a href="#modules--documentation">Modules & Docs</a>
</p>

</div>

---

Database schemas lack business meaning, and feeding raw documents to LLMs leads to metric drift. **OntoFoundry** unifies business specifications, database metadata, and human review into one versioned semantic layer consumable by both AI agents and applications.

## Core Capabilities

| Pillar | What You Get |
| --- | --- |
| **Core-1 Semantic Model** | Express object types (single-parent `is-a` inheritance & membership branches), properties, shared `ValueType` constraints, binary links, rules, standalone metrics (`simple` / `ratio` / `expression`), and physical mappings decoupled from SQL execution quirks |
| **Proposal-First Governance** | Both AI extraction and manual edits stage as reviewable proposals backed by material line numbers / SHA-256 checksums or table receipts; accept-time validation enforces completeness & single-object rules before 3-way merge into immutable versions |
| **Multi-Source Read-Only Binding** | Native read-only connectors for **PostgreSQL, MySQL, and Apache Doris**; supports physical tables, `sqlglot`-verified read-only SQL datasets, `snapshot_date_column` semantics, and live metric SQL preview |
| **MCP Gateway & Feedback Loop** | Personal-token cross-workspace MCP gateway and workspace-scoped MCP server ready for **Claude Code, Codex, OpenCode, and ZCode**, complete with gateway audit logs and `submit_feedback` correction reporting |
| **Enterprise Security & Standards** | Local auth + pluggable SSO hook, workspace RBAC, and scoped personal tokens; **Apache Ossie** schema-validated bidirectional adapter with itemized translation reports plus lossless Core-1 archive packages |

---

## Architecture

```mermaid
flowchart TB
    subgraph Inputs["Inputs & Data Sources"]
        M["Business Materials (Markdown / TXT / JSON / YAML / CSV)"]
        DB["Read-Only Databases (PostgreSQL / MySQL / Apache Doris)"]
        STD["External Models (Apache Ossie / Core-1 Native)"]
    end

    subgraph Core["OntoFoundry Platform Core"]
        AI["AI Modeling Bridge (Optional DataAgent)"]
        PW["Proposal Workbench (Provenance · Accept-Time Checks · Conflict Resolution)"]
        MODEL["Core-1 Engine (Inheritance · Metrics · Mappings · Facts · 3-Way Merge)"]
        AUTH["Enterprise Guardrails (Login/SSO · RBAC · PAT · Read-Only SQL)"]
    end

    subgraph Consumers["Serving & Consumer Ecosystem"]
        GW["MCP Gateway /api/v1/mcp & Workspace MCP"]
        REST["Versioned REST API & Exports"]
        AGENTS["Claude Code / ZCode / Codex / OpenCode / BI Apps"]
    end

    M --> AI -->|"Proposals"| PW
    DB -->|"Metadata sync & sqlglot checks"| MODEL
    STD -->|"Validated import"| MODEL
    PW -->|"Validated writes to draft"| MODEL
    MODEL --> AUTH --> GW --> AGENTS
    AUTH --> REST --> AGENTS
    AGENTS -->|"submit_feedback corrections"| PW
```

---

## Quick Start

> OntoFoundry runs standalone without any external LLM or DataAgent service — manual modeling, Ossie import/export, data mapping, metric preview, version publishing, and MCP serving all work out of the box.

### Docker Compose (2-Minute Setup)

Requires Docker and Docker Compose:

```sh
git clone https://github.com/opendata-lab/ontofoundry.git
cd ontofoundry
cp .env.example apps/api/.env
make compose-up
```

Alembic migrations run automatically on startup. Access the platform at:

- **Web Console**: http://127.0.0.1:8010
- **API Docs (Swagger)**: http://127.0.0.1:8910/docs (Health check: http://127.0.0.1:8910/healthz)

> [`.env.example`](.env.example) defaults to `ONTOFOUNDRY_AUTH_MODE=dev` and `ONTOFOUNDRY_SEED_DEMO=true` (pre-seeding a fictional sample workspace without login). For production or team deployments, set `ONTOFOUNDRY_AUTH_MODE=login` (default admin `admin` / `admin123`) and `ONTOFOUNDRY_SEED_DEMO=false`. Use `make compose-down` to stop services or `make compose-reset` to wipe volumes.

<details>
<summary><b>More Options: Source Dev · Offline Package · Production Config & Tests</b></summary>

#### Run from Source (Python 3.13 + uv · Node.js 22.19+ · PostgreSQL 17)

```sh
cp .env.example apps/api/.env
make install
docker compose up -d postgres
(cd apps/api && uv run --python 3.13 alembic -c src/ontofoundry_api/alembic.ini upgrade head)
make api-dev     # Backend :8000
make web-dev     # Second terminal, Frontend :5174
# Single process: stop make api-dev first, then make build && make serve (:8000)
```

#### Offline / Air-Gapped Package

Download a package and its `.sha256` from [GitHub Releases](https://github.com/opendata-lab/ontofoundry/releases), or build locally with `./scripts/create-offline-package.sh`. The commands below use `ontofoundry-offline-latest.tar.gz` from [`latest`](https://github.com/opendata-lab/ontofoundry/releases/tag/latest) (newest main build); versioned releases name it `ontofoundry-offline.tar.gz`:

```sh
shasum -a 256 -c ontofoundry-offline-latest.tar.gz.sha256
tar -xzf ontofoundry-offline-latest.tar.gz && cd offline
cp .env.example .env && ./install.sh
```

#### Production Guardrails

- Full configuration reference: [`.env.example`](.env.example) and [`config.py`](apps/api/src/ontofoundry_api/config.py).
- `ONTOFOUNDRY_ENVIRONMENT=production` requires `ONTOFOUNDRY_AUTH_MODE=login`, `ONTOFOUNDRY_SEED_DEMO=false`, `ONTOFOUNDRY_COOKIE_SECURE=true` behind HTTPS, and a 32+ character `ONTOFOUNDRY_SESSION_SECRET`.
- **Change `ONTOFOUNDRY_MCP_TOKEN`**: the default `ontofoundry-mcp-default-token` is public and startup checks do not reject it. Set a random value, or set it empty to disable the per-workspace MCP endpoint.
- Use read-only accounts for business databases: the SQL whitelist is an application-level guard, and connection passwords are stored as-is in the platform database.
- Local users, the SSO hook contract, platform admins and the username-collision risk, plus upgrade and legacy OAuth migration notes: see [docs/deployment.md](docs/deployment.md) (Chinese). Templates live in [`deploy/docker/ontofoundry/`](deploy/docker/ontofoundry/).

#### Tests & Verification

```sh
make lint   # Python ruff + Frontend eslint
make test   # API pytest + Frontend vitest
make build  # TypeScript type-check + Vite production build
```

Default API tests use an isolated SQLite database. For PostgreSQL transaction, migration and concurrency tests, provide an account that can create databases (CREATEDB):

```sh
cd apps/api
ONTOFOUNDRY_TEST_POSTGRES_URL='postgresql+psycopg://user:password@127.0.0.1:5432/test_db' \
  uv run --python 3.13 pytest -q
```

</details>

---

## AI & MCP Integration

### 1. Ground External AI Agents via MCP

The repository bundles [`plugins/ontofoundry/`](plugins/ontofoundry/README.md) (with the `ontology-grounding` skill and `.mcp.json`) so coding and analytics agents inspect published metrics, objects, and mappings before writing queries:

```text
# Install in Claude Code (gateway URL: https://<your-host>/api/v1/mcp; issue PAT in Personal Center -> Personal Tokens)
/plugin install ontofoundry --marketplace opendata-lab/ontofoundry
```

Also supports **ZCode, Codex, and OpenCode** — see [`plugins/ontofoundry/README.md`](plugins/ontofoundry/README.md) for client configuration snippets.

| Endpoint | Auth | Tools / Purpose |
| --- | --- | --- |
| `POST /api/v1/mcp` | Personal Access Token (PAT) | Cross-workspace gateway: `list_spaces`, `search_ontology`, `get_ontology`, `submit_feedback` |
| `POST /api/v1/workspaces/{workspace_id}/mcp` | `ONTOFOUNDRY_MCP_TOKEN` / run token | Single-workspace ontology & entity resolution: `search_ontology`, `get_ontology`, `search_objects`, `get_object`, `resolve_entity` |
| `GET /api/v1/mcp/workspaces` | Bearer token | Lists readable workspaces and current published versions |

### 2. AI-Assisted Modeling via OpenDataWorks DataAgent (Optional)

Configure `ONTOFOUNDRY_DATAAGENT_BASE_URL` and `ONTOFOUNDRY_DATAAGENT_AGENT_ID` in `apps/api/.env` and install the skills from [`integrations/dataagent/README.md`](integrations/dataagent/README.md) to extract ontology proposals interactively from 10k+ line materials and 100+ database tables.

---

## Modules & Documentation

| Path / Doc | Description |
| --- | --- |
| [`apps/api/`](apps/api/) · [`apps/web/`](apps/web/) | FastAPI backend (Core-1 engine, adapters, Alembic) & React 19 + Ant Design 5 workbench |
| [`plugins/ontofoundry/`](plugins/ontofoundry/README.md) | Client plugin for Claude Code, ZCode, Codex, and OpenCode |
| [`integrations/dataagent/`](integrations/dataagent/README.md) | OpenDataWorks DataAgent modeling/QA skills & offline package builder |
| [`docs/concepts/`](docs/concepts/README.md) | Core-1 conceptual reference (objects, inheritance, value types, links, metrics, rules, snapshots — Chinese) |
| [`docs/design/`](docs/design/2026-10-14-core-model-and-format-adapters.md) | Design baselines ([Core-1](docs/design/2026-10-14-core-model-and-format-adapters.md) · [Proposal Lifecycle](docs/design/2026-09-26-proposal-first-ontology-lifecycle-implementation-design.md) · [Agent Semantic Layer](docs/design/2026-11-11-runtime-agnostic-semantic-layer-for-agents.md) — Chinese) |
| [`docs/demo/coffee-channel-sales/`](docs/demo/coffee-channel-sales/README.md) | End-to-end walkthrough: top-down & bottom-up modeling + MCP analytics (Chinese) |
| [Platform design](docs/design/2026-09-01-enterprise-ontology-intelligence-platform-design.md) · [Ossie coverage matrix](docs/design/2026-10-08-ossie-coverage-matrix.md) | Overall product & architecture design; field-by-field Ossie round-trip coverage |
| [`docs/deployment.md`](docs/deployment.md) | Production config, login & SSO, upgrade and migration notes (Chinese) |
| [`docs/releases/`](docs/releases/) | Release notes (see also [`Known Issues`](docs/known-issues.md) · [`TODO`](docs/TODO.md)) |

---

## Scope & Roadmap

OntoFoundry focuses on **governed semantic definitions, data mappings, and read-only ontology serving** rather than replacing ETL or transactional systems: general-purpose Action execution, scheduled materialization, and cross-database SQL join compilation remain out of scope (consuming agents query each source per published ontology definitions). Upcoming milestones include **MCP OAuth 2.0 (PKCE)**, **per-object-type generated MCP tools**, and write-proposal MCP support — tracked in [`docs/TODO.md`](docs/TODO.md).

---

## Contributing & License

Issues and Pull Requests are welcome via [GitHub Issues](https://github.com/opendata-lab/ontofoundry/issues). Please follow [`AGENTS.md`](AGENTS.md) and ensure `make lint`, `make test`, and `make build` pass before submitting changes.

Licensed under [Apache License 2.0](LICENSE). Bundled notices reside with Apache Ossie ([`LICENSE`](apps/api/src/ontofoundry_api/adapters/ossie/assets/vendor/apache-ossie/LICENSE) · [`NOTICE`](apps/api/src/ontofoundry_api/adapters/ossie/assets/vendor/apache-ossie/NOTICE)) and DataAgent shared skills ([`LICENSE`](integrations/dataagent/shared/LICENSE) · [`NOTICE`](integrations/dataagent/shared/NOTICE)).
