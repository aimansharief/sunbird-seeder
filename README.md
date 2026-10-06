# sunbird-seeder

Creates benchmark test data in Sunbird Spark through its APIs, then exports CSVs for the JMeter load tests. Every stage is resumable: rerunning skips finished items and retries failed ones.

## Highlights

| Item | Value |
|---|---|
| Entities | users, Live content, Live courses, one batch per course, enrolments |
| State | `output/<run_id>/state.db` (SQLite) |
| JMeter input | `output/<run_id>/csv/` |
| Default volumes | 10,000 users, 1,000 contents, 105 courses, 52,500 enrolments |
| Before first run | Verify every endpoint and payload against your Spark deployment |

## Setup

Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # fill in secrets
pytest                      # runs against a fake Sunbird, no network
```

| Secret (`.env`) | Purpose |
|---|---|
| `SUNBIRD_API_KEY` | Kong API key, sent as `Authorization: Bearer` |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Keycloak login for the seeding admin |
| `ADMIN_USER_ID` | Sunbird user ID of that admin, used as `createdBy` |
| `KEYCLOAK_CLIENT_SECRET` | Secret of the admin Keycloak client (`admin_client_id`) |
| `TEST_USER_PASSWORD` | Password set on every seeded user |

The admin account needs roles to create users, create and review content, publish, and create batches.

## Before the first run

| Check | Where |
|---|---|
| `mode`: `public` (Kong) or `local` (internal services) | `config/bench.yaml` → `mode` |
| Endpoint paths and methods | `config/bench.yaml` → `endpoints` (public), `local` (local) |
| Request bodies and required fields | `src/seeder/payloads/builders.py` |
| Response fields read for IDs | `src/seeder/api/*.py` |
| Keycloak clients allow password grant | `config/bench.yaml` → `keycloak` |
| Channel, root org, framework IDs | `config/bench.yaml` |
| Whether enrol needs the learner's token | `config/bench.yaml` → `enrol_as` |

Then seed a small run first: set `run_id: smoke01` and small numbers in `config/volumes.yaml`.

## Workflow

Run stages in this order. Each depends on the previous one.

| Step | Command | Done when |
|---|---|---|
| 1 | `seeder seed users` | user status `created` |
| 2 | `seeder seed content` | content status `live` (polls async publish) |
| 3 | `seeder seed courses` | course status `live`; needs its child content Live |
| 4 | `seeder seed batches` | batch status `created`; needs Live course |
| 5 | `seeder seed enrolments` | enrolment status `enrolled` |
| 6 | `seeder verify` | all rows show `OK` |
| 7 | `seeder tokens` | fresh learner tokens in the store |
| 8 | `seeder export --workers 4` | CSVs written |

`seeder seed all` runs steps 1 to 5. A stage exits with code `1` if any item failed; run it again to retry. `verify` lists recent errors.

Run `tokens` and `export` shortly before each load test, since tokens expire. `seeder tokens --max-age-min 20` refreshes only older tokens.

## Outputs

| File | Columns | JMeter test |
|---|---|---|
| `content.csv` | `contentId` | Content Read |
| `courses.csv` | `courseId` | Course Hierarchy |
| `users_workerN.csv` | `userId`, `userName`, `accessToken` | User Profile Read |
| `enrolments_workerN.csv` | `userId`, `courseId`, `batchId`, `contentIds`, `accessToken` | Read / Update Content State |

`content.csv` and `courses.csv` repeat IDs with Zipf-like weighting, so a few IDs are hot. Tune `export.skew` (`0` is uniform) and `export.read_rows`. Per-user files are split by worker with no user on two workers; copy `_workerN` files to JMeter worker N. `contentIds` is pipe-separated.

## Layout

| Path | Purpose |
|---|---|
| `config/bench.yaml` | Environment, endpoints, concurrency, polling |
| `config/volumes.yaml` | `run_id`, entity counts, export settings |
| `assets/sample_content.pdf` | File uploaded for each content item |
| `src/seeder/cli.py` | Commands |
| `src/seeder/client/` | HTTP client with retries; Keycloak tokens |
| `src/seeder/api/` | One wrapper per Sunbird API area |
| `src/seeder/payloads/builders.py` | Request bodies |
| `src/seeder/stages/` | Stage logic and status transitions |
| `src/seeder/state/store.py` | SQLite state |
| `src/seeder/plan.py` | Naming and assignment of content to courses, users to batches |
| `src/seeder/export/` | CSV export and hot/long-tail weighting |
| `tests/` | Unit tests and an end-to-end test against a fake server |

## Status transitions

| Entity | Statuses |
|---|---|
| user | `created` |
| content | `created` → `uploaded` → `in_review` → `publish_requested` → `live` |
| course | `created` → `hierarchy_updated` → `in_review` → `publish_requested` → `live` |
| batch | `created` |
| enrolment | `enrolled` |

A failed step keeps the last good status and records the error, so the next run resumes from that step.

## Cleanup

`seeder cleanup --yes` retires seeded courses and content. Users, batches and enrolments are not removed; seeded names start with `run_id` so they are identifiable.

## Inspecting state

```bash
sqlite3 output/bench01/state.db \
  "SELECT kind, status, COUNT(*) FROM entities GROUP BY 1, 2;"
```
