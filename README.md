# Learning Loop Engine

An API-first university learning system, developed in daily, testable increments. The target loop is: identify a learning gap → choose an instructional sequence → deliver activities → collect evidence → update the learner model → choose again.

**Current milestone: Day 5 learners and isolation.** Implemented: MySQL course lifecycle APIs, domain authoring, validated immutable published prerequisite graphs, pseudonymous learners, published-version enrollments, unknown initial skill state, development roles and object ownership checks, health checks, OpenAPI documentation, migrations, and automated tests. The adaptive engine and activity generator are planned modules, not implemented features.

## Start here

1. Read [the scope and unresolved decisions](docs/01-scope.md).
2. Follow [the daily development plan](docs/04-daily-plan.md). It assumes one developer working 3–6 hours daily, with two hours already spent on Day 1.
3. Run [the Day 5 walkthrough](docs/11-day-5.md); [Day 4](docs/10-day-4.md) covers publishing, [Day 3](docs/09-day-3.md) covers domain authoring, [Day 2](docs/06-day-2.md) covers course lifecycle and [Day 1](docs/05-day-1.md) covers the foundation.
4. Use [the progress log](docs/daily-updates.md) for daily reporting.

## Run locally

Docker Desktop must be running. Docker supplies the exact Python 3.9.21 runtime and MySQL 8.4; your host Python only needs to run the credential setup script.

```bash
python3 scripts/init_local_env.py
docker compose up --build -d --wait api
docker compose --profile test run --build --rm tests
```

- Interactive API documentation: <http://localhost:8000/docs>
- API specification: <http://localhost:8000/openapi.json>
- Liveness: <http://localhost:8000/health/live>
- Readiness, including migrated database access: <http://localhost:8000/health/ready>

Use the `API_KEY` value from the local `.env` in Swagger's **Authorize** dialog, or send it in `X-API-Key`. It identifies `dev-author`, who owns migrated Day 1 courses. Setup preserves existing credentials and supplies instructor, two synthetic learner, and integration principals. These credentials must stay local. Additional roles can read the registry; only a course's author can edit or archive it. Learner routes require a learner key and expose only that principal's own records.

```bash
# An API-only demo; uses the key from .env without printing it.
python3 scripts/demo_day1.py
python3 scripts/demo_day2.py
python3 scripts/demo_day3.py
python3 scripts/demo_day4.py
python3 scripts/demo_day5.py --course-id 902a24a1-efa5-4172-a261-527f89e03c63 --domain-version-id 3288966b-a0cf-440b-8520-582f52cc88fa

# Confirm exact runtime and inspect service state.
docker compose exec api python --version
docker compose ps

# Stop services; the application database volume remains intact.
docker compose --profile test down
```

Host development is optional: install Python **3.9.21**, create `.venv`, install `requirements-dev.txt`, start the database with `docker compose up -d --wait db`, then run `.venv/bin/alembic upgrade head` and `.venv/bin/uvicorn app.main:app --reload`. Do not run a host API and the container API on port 8000 at the same time. `.env` targets the host database port 3307; Compose overrides the database address internally.

## Implemented API

| Method | Route | Purpose |
|---|---|---|
| GET | `/health/live` | Process health, no database required |
| GET | `/health/ready` | Migrated course table is reachable |
| POST | `/api/v1/courses` | Create a course; returns 201 and Location |
| GET | `/api/v1/courses?limit=20&offset=0&status=active` | List courses, ordered by code; supports active/archived/all |
| GET | `/api/v1/courses/{uuid}` | Retrieve one course |
| PATCH | `/api/v1/courses/{uuid}` | Author edits supplied fields on an active course |
| POST | `/api/v1/courses/{uuid}/archive` | Author archives a course; retries return the same record |

All course routes require `X-API-Key`. Course codes normalize to uppercase. Duplicate codes and edits after archival return 409; missing records return 404; invalid input returns 422; missing or invalid keys return 401; denied roles or ownership return 403. Database errors return a sanitized 503. Archived courses remain readable and retain their codes. No hard-delete route exists. See [API conventions](docs/07-api-contract.md) and [identity integration design](docs/08-identity-design.md).

There are 17 domain operations under `/api/v1/courses/{course_id}/domain-versions`: create/list/read versions; create/list/read/edit competencies and skills; create/list/read/remove draft prerequisite links; validate and publish a domain. See [the Day 3 walkthrough](docs/09-day-3.md) for authoring and [Day 4](docs/10-day-4.md) for graph and publication examples. All development roles may read and validate this synthetic domain metadata; only the course owner can author and publish active-course drafts. Publishing fixes the version's content and records a UTC timestamp.

Every application operation will be available through APIs, including authoring, imports, learner state, generation, attempts, and reporting. Database migrations, backups, and infrastructure configuration remain operator tasks; they are not public application endpoints.

Day 5 adds six learner operations: register the authenticated learner with `POST /api/v1/learners` and `{}`; read `/learners/{learner_id}`; create/list `/learners/{learner_id}/enrollments`; read an individual enrollment and its `/state`. Enrollment POST takes `course_id` and `domain_version_id`, requires an active course and published version, and initializes every skill as `unknown` with zero evidence and revision. Repeated registration/enrollment returns the existing row (200); first creation returns 201 and Location. Learners receive 404 for another learner's records, and author/instructor/integration roles without learner authority receive 403. State has no write endpoint. See [Day 5](docs/11-day-5.md) for examples and current enrollment limits.

## Project map

```text
app/                  API, configuration, data models, database sessions
migrations/           Versioned Alembic schema changes
tests/                API contract and real MySQL integration checks
scripts/              Local credential setup and API demo
docs/                 Scope, architecture, schema, daily plan, updates
compose.yaml          Local app and separate disposable test database
.python-version       Required interpreter version
requirements*.txt     Pinned runtime and test dependencies
```

See [architecture](docs/02-architecture.md) and [schema design](docs/03-schema.md) for the intended system. The implemented tables are `courses`, `domain_versions`, `competencies`, `skills`, `skill_prerequisites`, `learners`, `enrollments`, and `learner_skill_states`.

## Engineering constraints

Python 3.9.21 is retained because it is an explicit project requirement. Python 3.9 reached end of life on October 31, 2025; FastAPI 0.129.0 dropped Python 3.9. This project pins FastAPI 0.128.8 and compatible dependencies. Production rollout requires the university to resolve the unsupported runtime constraint and complete dependency review. Sources: [Python lifecycle](https://devguide.python.org/versions/), [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/).

This is a local synthetic-data prototype. Development keys enforce roles, course ownership and learner isolation; university identity, instructor assignments and integration grants remain future work before real learner data. The current Docker image includes test tools for development; a minimal production image is a later deliverable. Dependencies are pinned, but the MySQL 8.4 tag and base image still need digest pinning for a production release.
