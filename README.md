# sunbird-seeder

Creates test data in Sunbird Spark (users, Live content, Live courses, batches, enrolments) through its APIs, and exports CSVs for the JMeter load tests. Rerunning any step skips finished items and retries failed ones.

## 1. Configuration

**Secrets** go in `.env`. Copy `.env.example` to `.env` and fill in:

| Key | Description |
|---|---|
| `SUNBIRD_API_KEY` | Kong API key |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Admin login that creates the data |
| `KEYCLOAK_CLIENT_SECRET` | Secret of the Keycloak client (`keycloak.client_id`) |
| `ADMIN_USER_ID` | Admin's Sunbird user ID (not needed for users) |
| `CONTENT_CREATOR_USERNAME`, `_PASSWORD`, `_ID` | Creator account: creates content, courses and batches. Empty = admin |
| `CONTENT_REVIEWER_USERNAME`, `_PASSWORD`, `_ID` | Reviewer account: publishes content and courses. Empty = admin |
| `TEST_USER_PASSWORD` | Password given to every seeded user |

The admin needs the role to create users. The creator and reviewer need roles to create and to publish content; without them, the admin needs those roles too.

**Environment** goes in `config/bench.yaml`:

| Key | Description | Example |
|---|---|---|
| `mode` | `public` = through Kong, `local` = direct to services | `public` |
| `base_url` | Sunbird host | `https://your-spark-host` |
| `keycloak` | Keycloak URL, realm and `client_id` used for every login | `https://your-spark-host/auth` |
| `channel` | Channel for users, content and courses | `sunbird` |
| `framework` | Framework for content and courses | `NCF` |
| `root_org_id` | `createdFor` on courses and batches | - |
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
| Write JMeter CSVs | `seeder export --workers 4` |

Run the seed steps in order, or all at once with `seeder seed all`. If a step reports failures, run it again.

Users are named `user1_<run_id>`, `user2_<run_id>`, ... with display name `User 1`, `User 2`, ...

## Output

Everything is written to `output/<run_id>/`: progress in `state.db`, CSVs in `csv/`.

| File | Used by |
|---|---|
| `content.csv` | Content Read |
| `courses.csv` | Course Hierarchy (`courseId`, `contentIds` = comma-separated content ids in the course, quoted by the CSV writer) |
| `users_workerN.csv` | User Profile Read |
| `enrolments_workerN.csv` | Read / Update Content State |

Copy each `_workerN` file to JMeter worker N.

The `_workerN` files carry `userName` and `password` instead of tokens, so JMeter logs each user in at test time. The password is `TEST_USER_PASSWORD`; share these files only with the load-test team.

## Cleanup

`seeder cleanup --yes` retires the seeded content and courses. Users, batches and enrolments are not removed.
