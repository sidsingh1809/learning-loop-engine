# Verification log

## Day 5 — October 5, 2026

| Check | Actual result |
|---|---|
| Host contract suite | 126 passed; supplemental host-only checks |
| `docker compose --profile test run --build --rm tests` | 159 passed; no skipped tests; final run 4.54 seconds |
| Migration lifecycle in disposable test database | Fresh upgrade/base downgrade; earlier migration paths; 0005 downgrade to 0004/re-upgrade with full retained course/domain snapshots; Alembic schema comparison passed |
| Live runtime and learner storage | Python 3.9.21; head `0005_learners`; two learners, two enrollments, twelve initial state rows |
| Local application migration | Full pre/post snapshots matched for six courses, four domains, four competencies, thirteen skills and five prerequisite links, including publication timestamps |
| `docker compose up --build -d --wait api` | Migration completed; application database and API healthy |
| `python3 scripts/demo_day5.py --course-id 902a24a1-efa5-4172-a261-527f89e03c63 --domain-version-id 3288966b-a0cf-440b-8520-582f52cc88fa` | Two learners/enrollments created through HTTP; six unknown/zero-evidence skills each; own reads/retries passed; mutual record access and cross-learner enrollment denied (404); author state access denied (403) |

The suite adds learner authentication and role checks, forbidden identity/proficiency fields, no write APIs for state, pseudonymous responses, ignored spoofing headers, case-sensitive identity uniqueness, mutual object isolation, nested enrollment-parent isolation, pagination/missing resources, course/domain mismatch, draft/archived enrollment rejection, single-course version conflicts, stable retries and retained reads after course archival. Direct MySQL checks reject duplicate learner/course enrollment and either cross-version state boundary. A failed state insert verifies that neither enrollment nor partial state commits. Concurrent checks verify three registrations and three enrollments produce one record each, with one 201 and two 200 responses. Multi-role author/learner access still requires learner ownership.

The first MySQL run passed 156 checks and exposed a repeatable-read snapshot issue in concurrent enrollment: the initial learner read opened an older snapshot, causing the later non-locking enrollment lookup to miss a newly committed row. The enrollment lookup now uses a locking read inside the shared course/domain lock order. Final review also added a regression that publishes an extra skill after enrollment opens its identity snapshot: the skill lookup now uses a current locking read and initializes every published skill. The final suite passed all 159 checks. These concurrent checks establish targeted correctness, not a load/throughput claim.

The live demo reused the existing published pilot rather than rewriting its graph. It created learners `5b6b5593-48a7-453e-8b28-e601773f94ea` and `3dace22d-3366-434b-87e8-cd3e88f15f82`, each with an enrollment bound to domain `3288966b-a0cf-440b-8520-582f52cc88fa`. The pilot currently has six skills; all twelve state rows start unknown, with evidence count and revision zero. This differs from the five-skill automated fixture because the retained pilot already had additional authored content before this session. All pre-existing application records matched their complete snapshots after migration. Existing credentials were preserved; one missing synthetic learner credential was added without printing keys. The API and database remain running locally.

University identity, instructor assignments and integration grants remain planned. No real student data, diagnostic, evidence scoring, planner, generator or AI provider calls were used. Unknown state does not assert low proficiency. State updates require the later evidence migration/contract; Day 5 downgrade destroys learner/enrollment/state data and is tested only in the disposable database.

## Day 4 — October 3, 2026

| Check | Actual result |
|---|---|
| Host contract suite | 103 passed; 24 MySQL tests deselected |
| `docker compose --profile test run --build --rm tests` | 127 passed; no skipped tests; final run 2.96 seconds |
| Migration lifecycle in disposable test database | Fresh upgrade/base downgrade; existing Day 1/2 course metadata and Day 3 draft/competency/skill content preserved through 0004 upgrade, downgrade to 0003 and re-upgrade; earlier downgrade paths and Alembic schema comparison passed |
| Local application migration | Existing six courses, three domains, three competencies and eleven skills matched complete pre/post snapshots; migration head is `0004_domain_publishing` |
| `docker compose up --build -d --wait api` | Migration completed; API and application database healthy |
| `docker compose exec -T api python --version` | Python 3.9.21 |
| `python3 scripts/demo_day4.py --course-id 902a24a1-efa5-4172-a261-527f89e03c63 --domain-version-id 3288966b-a0cf-440b-8520-582f52cc88fa` | Four prerequisite links created through HTTP; self-link/cycle rejected; graph validated; learner publish denied; author publish/read/retry passed; published skill edit rejected |

The suite now covers same-version prerequisite CRUD (draft deletion only), pagination, missing and mismatched parents, self/duplicate/cyclic edge rejection, role and ownership denial, archived-course protection, incomplete publication with unchanged draft state, published content immutability, retained metadata reads/validation, and fresh empty revisions. Direct MySQL checks reject either foreign-version endpoint, duplicate links and self-links. Publication rechecks a deliberately corrupted cyclic draft seeded only in the disposable database. An iterative graph test validates 1,500 skills without recursion and checks deterministic ordering/multiple roots.

Concurrent request checks cover opposing edges (one 201 and one 409), graph insertion racing publication (committed before publishing or rejected after), and three publication requests returning the same stored representation. These are correctness checks, not throughput/load measurements or a complete archive/edit concurrency matrix. Cycles and immutability are service invariants; direct operator SQL can bypass them.

The first MySQL run passed 126 checks and exposed a test expectation mismatch: MySQL CHECK violations are reported by this driver as OperationalError (3819), while foreign-key violations use IntegrityError (1452). The test now checks each actual error code. The final complete suite passed all 127 checks.

The live demonstration reused active course `DAY3-F744D0673FBD` (UUID `902a24a1-efa5-4172-a261-527f89e03c63`) and domain `3288966b-a0cf-440b-8520-582f52cc88fa`. Its retained competency and five skills now have the provisional chain VARIABLES → EXPRESSIONS → CONDITIONALS → LOOPS → DEBUGGING. The domain is published with a UTC timestamp and no longer editable. Prior course, competency and skill content remained unchanged. Credentials were not printed. The API and database are left running for inspection.

No learner records, diagnostics, planner, generator, AI provider calls or real student data are implemented by this milestone. The Day 4 walkthrough and revised remaining-session estimate are in `10-day-4.md` and `04-daily-plan.md`. The original publication timestamp and graph links are lost by a Day 4 downgrade, so downgrade verification is confined to the disposable database.

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
