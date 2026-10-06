# sunbird-seeder

Creates test data in Sunbird Spark (users, Live content, Live courses, batches, enrolments) through its APIs, and exports CSVs for the JMeter load tests. Rerunning any step skips finished items and retries failed ones.

## 1. Configuration

**Secrets** go in `.env`. Copy `.env.example` to `.env` and fill in:

| Key | Description |
|---|---|
| `SUNBIRD_API_KEY` | Kong API key |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Admin login that creates the data |
| `KEYCLOAK_CLIENT_SECRET` | Secret of the admin Keycloak client |
| `ADMIN_USER_ID` | Admin's Sunbird user ID (not needed for users) |
| `TEST_USER_PASSWORD` | Password given to every seeded user |

The admin needs roles to create users, create, review and publish content, and create batches.

**Environment** goes in `config/bench.yaml`:

| Key | Description | Example |
|---|---|---|
| `mode` | `public` = through Kong, `local` = direct to services | `public` |
| `base_url` | Sunbird host | `https://your-spark-host` |
| `keycloak` | Keycloak URL, realm and admin client | `https://your-spark-host/auth` |
| `custodian_channel` | Channel name for new users | `sunbird` |
| `channel`, `root_org_id`, `framework` | Used for content and courses | - |
| `local.hosts` | Service URLs, `local` mode only | `http://localhost:9000` |

**Volumes** go in `config/volumes.yaml`: `run_id` and how many users, contents and courses to create. Start small, e.g. `run_id: smoke01` and `users: 2`.

## 2. Setup

Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest          # optional: runs against a fake Sunbird, no network
```

## 3. Run

| Step | Command |
|---|---|
| Create users | `seeder seed users` |
| Create content | `seeder seed content` |
| Create courses | `seeder seed courses` |
| Create batches | `seeder seed batches` |
| Enrol users | `seeder seed enrolments` |
| Check progress and errors | `seeder verify` |
| Get learner tokens | `seeder tokens` |
| Write JMeter CSVs | `seeder export --workers 4` |

Run the seed steps in order, or all at once with `seeder seed all`. If a step reports failures, run it again.

Run `tokens` and `export` just before each load test, since tokens expire.

Users are named `user1_<run_id>`, `user2_<run_id>`, ... with display name `User 1`, `User 2`, ...

## Output

Everything is written to `output/<run_id>/`: progress in `state.db`, CSVs in `csv/`.

| File | Used by |
|---|---|
| `content.csv` | Content Read |
| `courses.csv` | Course Hierarchy |
| `users_workerN.csv` | User Profile Read |
| `enrolments_workerN.csv` | Read / Update Content State |

Copy each `_workerN` file to JMeter worker N.

## Cleanup

`seeder cleanup --yes` retires the seeded content and courses. Users, batches and enrolments are not removed.
