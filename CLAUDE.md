# CLAUDE.md

Seed-data generator for the Sunbird Spark API benchmark. It creates users, Live content, Live courses, batches and enrolments through Sunbird APIs, tracks progress in SQLite, and exports CSVs that the JMeter load tests read.

## Benchmark context

| Item | Detail |
|---|---|
| Goal | Generate seed data (users, Live content, Live courses, batches, enrolments) and the CSVs used to benchmark 7 read/write APIs with JMeter |
| APIs under test | Content Read, Course Hierarchy, Content Search, User Profile Read, Read Content State, Update Content State, Telemetry |
| Run matrix | Internal route vs via Kong × self-hosted YugabyteDB vs managed YugabyteDB (Runs A–D) |
| Load tool | Distributed JMeter; each worker gets its own `_workerN` CSV |
| This repo's job | Produce the data and CSVs only. Load testing lives elsewhere |

Seed once through the APIs, then copy YugabyteDB to the managed instance with backup/restore. Re-seeding through the APIs produces different IDs and breaks the CSVs.

## Commands

| Task | Command |
|---|---|
| Install | `pip install -e ".[dev]"` |
| Tests (no network) | `pytest` |
| Seed one stage | `seeder seed users` / `content` / `courses` / `batches` / `enrolments` |
| Seed everything in order | `seeder seed all` |
| Check progress and errors | `seeder verify` |
| Write JMeter CSVs | `seeder export --workers N` |
| Retire seeded content/courses | `seeder cleanup --yes` |

## Architecture

| Path | Responsibility |
|---|---|
| `config/bench.yaml` | Environment, `mode` (`public` via Kong / `local` internal services), endpoints for each mode, concurrency, polling |
| `config/volumes.yaml` | `run_id`, entity counts, export weighting |
| `src/seeder/client/http.py` | Single HTTP client: headers, retry on 429/5xx/transport errors, refresh admin token on 401 |
| `src/seeder/client/auth.py` | Login for admin, content creator, reviewer and learners: Keycloak grant → `refresh_token` → `/auth/v1/refresh/token` → API access token |
| `src/seeder/api/` | Thin wrappers: build payload, call endpoint, parse IDs |
| `src/seeder/payloads/builders.py` | All request bodies |
| `src/seeder/stages/` | Orchestration and status transitions per entity |
| `src/seeder/stages/runner.py` | `run_all` (bounded concurrency, records errors) and `poll_until` (async publish) |
| `src/seeder/state/store.py` | SQLite `entities` table keyed by `(kind, key)` |
| `src/seeder/plan.py` | Pure functions: names, content→course and user→batch assignment, worker split |
| `src/seeder/export/` | CSV export: every Live ID and enrolment once; JMeter decides how to pick rows |

Dependency order: users and content are independent; content (Live) → course (Live) → batch → enrolment.

## Conventions

- SQLite is the source of truth during seeding; CSVs are generated from it at the end. Do not track state in CSVs.
- Every stage must be resumable. Skip items already at their final status; resume others from their last status.
- `store.upsert` records a successful step and clears the error. `store.mark_error` records a failure without changing status.
- Names are deterministic and include `run_id` (users: `user1_bench01`, display name "User 1"; others: `bench01_content_00001`). Assignment logic stays in `plan.py` with tests.
- Endpoints belong in `config/bench.yaml`, never hard-coded. Add each new endpoint to both `endpoints` (public) and `local.endpoints`. Request bodies belong in `payloads/builders.py`.
- Secrets come from `.env` only. Never commit `.env` or `output/`.
- New behaviour needs a test. `tests/test_end_to_end.py` uses a fake Sunbird via `httpx.MockTransport`; extend `FakeSunbird` when adding endpoints.

## Status transitions

| Entity | Statuses |
|---|---|
| user | `created` |
| content | `created` → `uploaded` → `publish_requested` → `live` (no review step) |
| course | `created` → `hierarchy_updated` → `in_review` → `publish_requested` → `live` |
| batch | `created` |
| enrolment | `enrolled` |

## Default volumes

10,000 users; 1,000 contents; 105 courses with 10 contents in 2 units; one batch per course; 500 users per batch = 52,500 enrolments (each user in 5–6 courses).

## Not yet verified against a real Spark deployment

| Item | Where |
|---|---|
| Endpoint paths, especially collection create/review/publish/read and hierarchy update | `config/bench.yaml` |
| Local service hosts, internal paths and which need `user_token` | `config/bench.yaml` → `local` |
| Request body fields (user create, content/course create, hierarchy, batch, enrol) | `payloads/builders.py` |
| Response fields used for IDs (`userId`, `identifier`, `batchId`) and user search shape | `api/*.py` |
| Keycloak `client_id`, password grant, and the refresh endpoint response shape (`result.access_token`) | `config/bench.yaml`, `client/auth.py` |
| Error text used to detect "already exists" / "already enrolled" | `api/users.py`, `api/enrolments.py` |

## Next steps

1. Fill `.env` and `config/bench.yaml` for the target environment.
2. Smoke run: `run_id: smoke01` with tiny volumes; fix endpoint/payload mismatches.
3. Full seed with `run_id: bench01`, then `seeder verify`.
4. Add `search_queries.csv` export for the Content Search test.
5. Consider larger volumes: the default dataset may fit in cache and understate DB differences.
