# Learning Loop Engine

An API-first university learning system, developed in daily, testable increments. The target loop is: identify a learning gap → choose an instructional sequence → deliver activities → collect evidence → update the learner model → choose again.

**Current milestone: Day 9 attempts, scoring and immutable evidence.** Implemented: MySQL course lifecycle, immutable published graphs, isolated learners/enrollments, reviewed activity/policy catalogs, explainable plans and validated template activities with instructor review before delivery. Learners can now submit immutable answers; selected responses receive server scores, while constructed responses require instructor rubric scoring. Evidence retains skill, rubric, scorer and activity/plan provenance. Learner-state application and the complete adaptive loop remain Day 10 work.

## Start here

1. Read [the scope and unresolved decisions](docs/01-scope.md).
2. Follow [the daily development plan](docs/04-daily-plan.md). It assumes one developer working 3–6 hours daily, with two hours already spent on Day 1.
3. Run [the Day 9 walkthrough](docs/15-day-9.md); [Day 8](docs/14-day-8.md) covers generation, [Day 7](docs/13-day-7.md) covers planning, [Day 6](docs/12-day-6.md) covers catalogs, [Day 5](docs/11-day-5.md) covers learners, [Day 4](docs/10-day-4.md) covers publishing, [Day 3](docs/09-day-3.md) covers domain authoring, [Day 2](docs/06-day-2.md) covers course lifecycle and [Day 1](docs/05-day-1.md) covers the foundation.
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
python3 scripts/demo_day6.py
# Internal planner fixtures, then optional live planning on the retained pilot:
.venv/bin/python scripts/demo_day7.py
.venv/bin/python scripts/demo_day7.py --course-id 902a24a1-efa5-4172-a261-527f89e03c63 --domain-version-id 3288966b-a0cf-440b-8520-582f52cc88fa

.venv/bin/python scripts/demo_day8.py
.venv/bin/python scripts/demo_day8.py --plan-id d4022c31-de90-4a82-bffa-3f9b9cda8bc9

.venv/bin/python scripts/demo_day9.py
.venv/bin/python scripts/demo_day9.py --plan-id d4022c31-de90-4a82-bffa-3f9b9cda8bc9

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
| GET | `/health/ready` | All eighteen migrated application tables are reachable |
| POST | `/api/v1/courses` | Create a course; returns 201 and Location |
| GET | `/api/v1/courses?limit=20&offset=0&status=active` | List courses, ordered by code; supports active/archived/all |
| GET | `/api/v1/courses/{uuid}` | Retrieve one course |
| PATCH | `/api/v1/courses/{uuid}` | Author edits supplied fields on an active course |
| POST | `/api/v1/courses/{uuid}/archive` | Author archives a course; retries return the same record |

All course routes require `X-API-Key`. Course codes normalize to uppercase. Duplicate codes and edits after archival return 409; missing records return 404; invalid input returns 422; missing or invalid keys return 401; denied roles or ownership return 403. Database errors return a sanitized 503. Archived courses remain readable and retain their codes. No hard-delete route exists. See [API conventions](docs/07-api-contract.md) and [identity integration design](docs/08-identity-design.md).

There are 17 domain operations under `/api/v1/courses/{course_id}/domain-versions`: create/list/read versions; create/list/read/edit competencies and skills; create/list/read/remove draft prerequisite links; validate and publish a domain. See [the Day 3 walkthrough](docs/09-day-3.md) for authoring and [Day 4](docs/10-day-4.md) for graph and publication examples. All development roles may read and validate this synthetic domain metadata; only the course owner can author and publish active-course drafts. Publishing fixes the version's content and records a UTC timestamp.

Every application operation will be available through APIs, including authoring, imports, learner state, generation, attempts, and reporting. Database migrations, backups, and infrastructure configuration remain operator tasks; they are not public application endpoints.

Day 5 adds six learner operations: register the authenticated learner with `POST /api/v1/learners` and `{}`; read `/learners/{learner_id}`; create/list `/learners/{learner_id}/enrollments`; read an individual enrollment and its `/state`. Enrollment POST takes `course_id` and `domain_version_id`, requires an active course and published version, and initializes every skill as `unknown` with zero evidence and revision. Repeated registration/enrollment returns the existing row (200); first creation returns 201 and Location. Learners receive 404 for another learner's records, and author/instructor/integration roles without learner authority receive 403. State has no write endpoint. See [Day 5](docs/11-day-5.md) for examples and current enrollment limits.

Day 6 adds twelve catalog operations under `/api/v1/catalog`: create/list/read immutable `/activity-versions` and `/policy-versions`, instructor `/review` actions, and approved-only `/activities` and `/policies` list/detail reads. Activities pin exact approved policy IDs and retain component mappings with rationale. Review is for synthetic prototype use only; university and expert review remain outstanding. See [Day 6](docs/12-day-6.md) for the contract and limits.

Day 7 adds `POST /api/v1/learners/{learner_id}/loop-plans` and `GET /api/v1/loop-plans/{plan_id}`. Plans use stored enrollment state, a requested target, exact approved policy IDs and a strict 1–180 minute budget. Responses preserve the input snapshot, deterministic rationale, focus/support, catalog IDs and connected steps. Identical input retries return the saved plan (200); first creation returns 201 and Location. Unknown remains distinct from low knowledge. Evidence-bearing beginner/experienced profiles are internal fixtures until Day 10 implements authoritative state updates. See [Day 7](docs/13-day-7.md).

Day 8 adds five operations: learner `POST /api/v1/loop-plans/{plan_id}/generations` with `{}`, learner `GET /api/v1/activity-generations/{generation_id}`, instructor `GET /api/v1/activity-generations/{generation_id}/review-content` and `POST /api/v1/activity-generations/{generation_id}/review`, and learner `GET /api/v1/activities/{activity_id}`. Generation saves an ordered candidate atomically (201), reuses it on retry (200), and withholds activity content until instructor approval. Rubrics align target/focus skills; scoring keys stay private. The first template covers the synthetic programming DEBUGGING pilot. See [Day 8](docs/14-day-8.md) for supported content and review limits.

Day 9 adds learner `POST`/`GET /api/v1/activities/{activity_id}/attempts`, learner `GET /api/v1/attempts/{attempt_id}`, and instructor `GET /api/v1/attempts/{attempt_id}/review-content` and `POST /api/v1/attempts/{attempt_id}/review`. Submissions require a UUID idempotency key and typed answer. Selected answers score on the server; written answers remain pending until a different instructor principal scores every saved rubric criterion. Scores/evidence are terminal and provisional; clients cannot supply authoritative scores. See [Day 9](docs/15-day-9.md) for retries, examples and boundaries.

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

See [architecture](docs/02-architecture.md) and [schema design](docs/03-schema.md) for the intended system. The eighteen implemented tables are `courses`, `domain_versions`, `competencies`, `skills`, `skill_prerequisites`, `learners`, `enrollments`, `learner_skill_states`, `policy_versions`, `activity_variants`, `component_activity_mappings`, `loop_plans`, `loop_steps`, `activity_generations`, `activities`, `attempts`, `attempt_scores` and `evidence`.

## Engineering constraints

Python 3.9.21 is retained because it is an explicit project requirement. Python 3.9 reached end of life on October 31, 2025; FastAPI 0.129.0 dropped Python 3.9. This project pins FastAPI 0.128.8 and compatible dependencies. Production rollout requires the university to resolve the unsupported runtime constraint and complete dependency review. Sources: [Python lifecycle](https://devguide.python.org/versions/), [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/).

This is a local synthetic-data prototype. Development keys enforce roles, course ownership and learner isolation; university identity, instructor assignments and integration grants remain future work before real learner data. The current Docker image includes test tools for development; a minimal production image is a later deliverable. Dependencies are pinned, but the MySQL 8.4 tag and base image still need digest pinning for a production release.
