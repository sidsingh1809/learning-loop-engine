# Verification log

## Day 3 — October 2, 2026

| Check | Actual result |
|---|---|
| Host contract suite | 75 passed; 15 MySQL tests deselected |
| `docker compose --profile test run --build --rm tests` | 90 passed; no skipped tests; final run 1.91 seconds |
| Migration lifecycle in disposable test database | Fresh upgrade/base downgrade; Day 1 content and Day 2 ownership/archive metadata preserved across 0003 upgrade and downgrade to 0002/re-upgrade; downgrade to 0001/re-upgrade also passed; Alembic schema comparison passed |
| `docker compose up --build -d --wait api` | Migration completed; API and database healthy |
| `docker compose exec api python --version` | Python 3.9.21 |
| `python3 scripts/demo_day3.py` | Live create/read/edit, learner write denial and duplicate-code demonstration passed |

The Day 3 suite covers request validation, strict booleans, immutable parent IDs, role denial and spoofed identity headers, authentication/OpenAPI declarations, paginated collections, unique normalized codes and atomic edit rollback, cross-course and cross-version resource isolation, direct database rejection of a cross-version skill, archived-course and non-draft write protection, resulting kind/automaticity validation, retained reads, and four concurrent version creations with distinct sequential numbers. Readiness requires the new domain tables as well as the course lifecycle columns.

The fixture seeds a published status only in the disposable test database to verify protective rejection. No publish endpoint is implemented. The concurrent-version test is a targeted correctness check, not a load test or a simultaneous archive/edit test.

The live demo created active course `DAY3-F744D0673FBD` (UUID `902a24a1-efa5-4172-a261-527f89e03c63`) and draft domain `3288966b-a0cf-440b-8520-582f52cc88fa`, with one competency and five classified skills. All data was authored through HTTP. The demo verified 201 creation, 200 read/edit, 403 learner write denial and 409 duplicate skill conflict. The draft remains active for Day 4. Existing demo courses and earlier migrations were not modified. Credentials were not printed.

The complete suite ran in the required Python 3.9.21 container against MySQL 8.4. Host checks and the HTTP demo are supplemental. No AI provider, real learner data, prerequisites, publishing, learner state, planner or generator is implemented by this milestone. The application API and database remain running locally.

## Day 2 — October 1, 2026

| Check | Actual result |
|---|---|
| Host contract suite | 36 passed; 6 MySQL tests deselected |
| `docker compose --profile test run --build --rm tests` | 42 passed; no skipped integration tests |
| Migration lifecycle in dedicated test database | Fresh upgrade/base downgrade; Day 1 row preserved through 0002 upgrade, downgrade to 0001, and re-upgrade; Alembic schema comparison passed |
| `docker compose up --build -d --wait api` | Additive migration completed; API and database healthy |
| `docker compose exec api python --version` | Python 3.9.21 |
| `python3 scripts/demo_day2.py` | Live lifecycle and role-denial demonstration passed |

The Day 2 suite covers partial edits, explicit-null/empty/invalid patch rejection, duplicate-code rollback, ownership isolation between two authors, read permissions, denied non-author writes, spoofed identity headers, rejected development credential configuration, retained archived records, repeated archival, blocked editing/deletion/code reuse after archival, filters and missing records. Readiness now checks the lifecycle columns so an unmigrated database cannot report ready.

The live demo added archived course `DAY2-8D65361CC692` (UUID `f68291d4-e6c8-4fdd-8c14-6615cbe0df17`) through HTTP. It verified 201 creation, 200 editing/archival/read, 403 learner edit/archive denial, 409 archived edit and duplicate-code conflicts, and 405 deletion rejection. Local credentials were not printed. Application data remains in its existing Docker volume.

The complete authoritative suite ran in the required container. The host-only suite and HTTP client are supplemental. Concurrency load testing, production identity, learner isolation and the learning loop remain outside this milestone. The row-lock strategy is implemented; this session did not run a simultaneous-request load test.

## Day 1 verification

Verified on September 30, 2026.

| Check | Actual result |
|---|---|
| `docker compose exec api python --version` | Python 3.9.21 |
| `docker compose up --build -d --wait api` | Database and API healthy; migration exited successfully |
| `docker compose --profile test run --build --rm tests` | 14 passed, no skipped integration tests |
| Migration lifecycle in dedicated test database | Upgrade, downgrade to base, re-upgrade and Alembic schema comparison passed |
| `python3.9 scripts/demo_day1.py` | Live POST returned 201; GET returned 200 with matching persisted course |
| `docker compose exec api python -m pip check` | No broken requirements found |

The suite covers API key rejection, input validation, code normalization, sanitized database failure responses, OpenAPI security declaration, MySQL persistence, duplicate-code conflicts, UTF-8 content, UTC timestamps, pagination and missing records.

The first real MySQL run exposed a create/read timestamp precision mismatch. Course creation now refreshes the persisted record before returning it. The round-trip test passes after that correction.

Host-only checks ran on Python 3.9.13; they are supplemental. The authoritative complete suite ran inside the required Python 3.9.21 container against MySQL 8.4.

No learner model, instructional planner, activity generator, evidence updater, educational evaluation, university SSO, load testing, or production deployment has been completed. No real learner data or paid generation API was used. Only a synthetic CS101 course was created through the local API.

The application API and database are left running locally for inspection. The separate disposable test database can be restarted by the test command. Application data persists in the project's Docker volume. See README for stop instructions.
