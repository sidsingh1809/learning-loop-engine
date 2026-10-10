# Verification log

## Day 10 — October 10, 2026

User verification: the developer reported completing all Day 10 terminal and Swagger tests on October 10, 2026. Developer time: 4 hours. This is user-reported verification; individual response payloads were not supplied in chat.

| Check | Measured result |
|---|---|
| `docker compose --profile test run --build --rm tests python -m pytest -q -x --tb=short` | **436 passed**, no skips; 22.13 seconds |
| Supplemental host suite | 345 passed; 91 MySQL checks deselected; 1.68 seconds |
| Runtime/database | Python 3.9.21; MySQL 8.4; local head `0010_state_application` |
| Complete loop | API-driven unknown → developing, selected practice, whole-task return → secure; updated next plan fades support; old snapshots retained |
| State policy | Versioned provisional threshold, failed observations distinct from unknown, at least two whole-task attempts, exact 80% boundary, part-task exclusion, multiple criteria count once per revision, poor whole-task evidence can lower band |
| Atomicity | State-update/history-insert failures roll back selected attempt/score/evidence and written score/evidence; written answer remains pending; historical batch failure rolls back every application; retry succeeds |
| Retries/concurrency | Identical submission/review replay adds no evidence or revisions; three different simultaneous reviews retain all revisions; concurrent historical synchronization applies two scores once, with counts 2/0/0 |
| Historical records | Day 9 evidence applies through explicit sync, next-plan request, exact submission retry or review retry; evidence rows remain unchanged; pending answers still need review |
| Authorization/integrity | Own-learner synchronization, role/foreign learner denial, override-field rejection; observed/secure SQL constraints, application enrollment/domain lineage and false certification flag enforced |
| Migration lifecycle | Fresh/base and existing lifecycle checks; populated Day 9 original columns/rows survive downgrade/re-upgrade; Alembic schema comparison passes; observed-state downgrade rejected before DDL |
| Local preservation | All 18 previous table counts and original-column row hashes match across migration, including 3 scores and 6 evidence rows; zero applications immediately after migration |
| Live walkthrough | Applied 3 historical scores; saved attempt `88f5d5f8-497a-4a68-81bb-fb4b167c23f9`; EXPRESSIONS unknown → developing and DEBUGGING revision 3 → 4; next plan `a0a269b5-5b49-4463-a5f2-4200f4c5e39f`; submission/review/plan/sync replay stable |

The retained synthetic learner now has VARIABLES secure (revision 3), EXPRESSIONS developing (revision 1), DEBUGGING secure (revision 4), and three remaining unknown skills. Four immutable applications trace the three historical scores and one new score. The new plan targets DEBUGGING while retaining EXPRESSIONS as its prerequisite focus. Whole-task counts are explicit; no part-task score was submitted in this live walkthrough. The disposable API integration test verifies the selected-practice path using evidence-created state.

These checks establish prototype transaction/idempotency behavior, not educational validity. Mastery thresholds remain provisional, repeated template attempts do not establish independence, and instructor approval is a synthetic workflow. University/expert review, policy calibration, context variation, continuity, AI provider integration, identity assignments and production readiness remain outstanding. The API/database remain healthy locally.

## Day 9 — October 9, 2026

User verification: the developer reported all Day 9 Swagger tests completed on October 9, 2026, following the submission, retry/validation, instructor scoring and learner-access walkthrough. This is user-reported verification; individual response payloads were not supplied in chat.

| Check | Measured result |
|---|---|
| `docker compose --profile test run --build --rm tests python -m pytest -q --disable-warnings --maxfail=1` | 410 passed; no skips; 16.75 seconds |
| Supplemental host suite | 333 passed; 77 MySQL checks deselected; 1.82 seconds |
| Runtime/database | Python 3.9.21; MySQL 8.4; local head `0009_attempts` |
| Submission/scoring | Immutable typed answers; correct/incorrect server scoring; written pending review; exact rubric coverage, partial credit and bounded integer points; private scoring keys withheld |
| Authorization | Learner-only submission/reads, cross-learner 404, spoofing denial, instructor-only review, multi-role self-review denial, selected-score override rejection |
| Retries/concurrency | One attempt under three identical concurrent submissions; one score/evidence set under three identical reviews; changed concurrent submissions/reviews produce one success and conflicts |
| Atomicity/integrity | Selected evidence failure leaves no new attempt/score/evidence; instructor evidence failure preserves pending attempt; MySQL score bounds/domain/lineage constraints pass; invalid/corrupted activity cannot create evidence |
| Migration lifecycle | Fresh/base and prior lifecycle checks; populated Day 8 rows survive 0009 downgrade/re-upgrade; Alembic schema comparison passes |
| Local migration preservation | All 15 prior table counts and complete row hashes match before/after migration |
| Live HTTP walkthrough | Saved attempt `32bcf5af-a8d4-4fc1-b292-dddf71335c47`; pending → instructor-scored; read/list/retry, 422 score rejection, 404 isolation, 403 review denial, 409 changed retries and unchanged state pass |
| Local service | `docker compose up --build -d --wait api` completed; API/database healthy; one attempt, one terminal score and two whole-task evidence rows retained |

Preserved tables contained six courses, four domains, four competencies, thirteen skills, five prerequisites, two learners, two enrollments, twelve unknown state rows, eight policies, eleven activity variants, twenty-five component mappings, two plans, four plan steps, one generation and two delivered activities. Only counts/hashes were emitted for preservation checking. The HTTP demo then added one synthetic attempt with its score and evidence through APIs, reusing existing credentials and approved content.

All 410 tests passed on the first complete Day 9 MySQL run. Pure and disposable-MySQL fixtures cover selected responses using internal developing-band plans; they never modify live learner bands. The live retained unknown-state plan has no selected question, so its HTTP demonstration follows constructed-response review. The saved evidence is provisional synthetic data, not substantive expert grading or university approval.

Learner-state rows, counts and revisions remain unchanged. Evidence application, provisional mastery policy and next-plan adaptation remain Day 10. No AI provider call, code execution, formal certification or real learner data is included. Instructor authority remains global in this development prototype; assignment-scoped university access remains future work. Downgrade deletes Day 9 evidence and is exercised only in the disposable database. See [Day 9](15-day-9.md) for the complete walkthrough and boundaries.

## Day 8 — October 9, 2026

User verification: the developer reported all Day 8 tests completed on October 9, 2026. Shared Swagger responses confirm instructor candidate inspection, unchanged approval retry, and learner delivery of both activities with private rubric answers omitted.

| Check | Measured result |
|---|---|
| `docker compose --profile test run --build --rm tests` | 352 passed, no skips; final run 13.78 seconds, Python 3.9.21 / MySQL 8.4 |
| Host supplemental suite | 290 passed before final five MySQL checks were added; Python 3.9.13 |
| Pure template walkthrough | Unknown: context → return, 16 minutes; beginner: context → routine practice → return, 19 minutes; experienced: whole task, 10 minutes |
| Migration lifecycle and Alembic comparison | Fresh/base lifecycle and populated Day 7 downgrade/re-upgrade passed; models match migration 0008 |
| Local additive migration | All 13 pre-existing table row hashes matched; two new empty tables before demo |
| Live `scripts/demo_day8.py --plan-id d4022c31-de90-4a82-bffa-3f9b9cda8bc9` | Generation 201; identical retry/read 200; learner isolation 404; unauthorized review 403; content override 422; pre-approval content 404; instructor inspection/review/retry and approved delivery 200 |
| Local API after migration | Ready and live; exact container runtime Python 3.9.21 |

The suite covers frozen sequence replay, target/focus and rubric alignment, policy/catalog provenance, full durations, return after support, explicit pilot limits, malformed output, duplicate/missing choice keys, rubric total/certification violations, private answer projection, API input/security contracts, concurrent generation and conflicting reviews, insert/review rollback, self-review denial, approved-only delivery, corruption withholding, archival behavior, composite SQL lineage and review constraints.

Pre/post migration snapshots retained six courses, four domains, four competencies, thirteen skills, five prerequisites, two learners, two enrollments, twelve unknown states, eight policies, eleven activity definitions, twenty-five mappings, two plans and four plan steps. Complete row hashes matched for every table before adding Day 8 demonstration records; migration 0008 adds only `activity_generations` and `activities`.

Live generation `f08a63e4-dc44-4f0d-a28d-a6cca1f4cb9d` belongs to the retained Day 7 plan and contains worked example `7854a5f9-9aec-4403-a2d5-b4fa646cf557` and whole-task return `28b4b9d9-e7a4-44b1-acf6-c2e59b518ae7`. Both use the same positive-sales debugging scenario and pinned target/focus. Development-instructor approval is a programmatic synthetic template/rubric inspection, not expert or university review. Every learner state matched its pre-demo value. Credentials and private scoring content were not printed.

No attempt scoring, evidence/state update, AI generation or real learner data was used. The template intentionally supports only the synthetic DEBUGGING pilot and named prerequisites. Content/rubric correctness, educational efficacy and university approval remain separate review gates. The API/database are left running; the new API contract is in local Swagger and [the Day 8 walkthrough](14-day-8.md).

## Day 7 — October 8, 2026

User verification: terminal and Swagger walkthrough completed, as reported by the developer on October 8, 2026.

| Check | Measured result |
|---|---|
| `docker compose --profile test run --build --rm tests python -m pytest -q --tb=short --maxfail=1` | 283 passed; no skips; final run 8.59 seconds |
| Runtime/database | Python 3.9.21 image; MySQL 8.4 |
| Pure planner fixtures | Unknown: VARIABLES guidance, 16 minutes; beginner: VARIABLES support/practice, 19 minutes; experienced: DEBUGGING independent task, 10 minutes; requested budget 25 |
| Determinism/provenance | Identical and reordered inputs yield identical decisions/fingerprints; exact graph/state/catalog/policy snapshot replay matches saved decision |
| Prerequisites/support | Transitive prerequisite selection; unrelated gaps ignored; unknown preserved; support fades with observed fixture bands; routine automaticity-only part-task practice |
| Budget/catalog rules | Full catalog duration retained; optional practice omitted at 16-minute beginner boundary; undersized connected sequences rejected; draft/rejected/wrong-policy/missing-mapping candidates excluded |
| API/storage | Ownership and parent isolation, spoofed-role rejection, strict request validation, immutable surface, exact retries, concurrent single-plan creation, atomic step-failure rollback and unchanged state |
| Migration lifecycle | Fresh/base and earlier lifecycle checks; populated Day 6 reviewed catalog and Day 5 learner rows survive 0007 downgrade/re-upgrade; Alembic schema comparison passes |
| Local migration | All 11 pre-existing table counts and complete row hashes match before/after 0007 |
| Local HTTP demo | Saved plan `d4022c31-de90-4a82-bffa-3f9b9cda8bc9`; create/read/retry/replay, 404 learner isolation, 403 role denial, 409 budget failure and unchanged state passed |
| `docker compose up --build -d --wait api` | Migration completed; application API/database healthy |

Preserved local rows: six courses, four domains, four competencies, thirteen skills, five prerequisites, two learners, two enrollments, twelve unknown state rows, eight policy versions, eleven activity variants and twenty-five component mappings. Only counts and hashes were emitted for preservation comparison. The live demo then created one plan with its connected steps through HTTP; existing graph, catalog, enrollment and state records were reused.

The first MySQL run passed 282 checks and exposed a concurrent read issue: after waiting for a newly created plan, a repeat request's ordinary relationship lookup could see the older repeatable-read snapshot and omit steps. Plan POST now uses a current locking step lookup; concurrent representations match. A subsequent migration-fixture run failed because Pydantic read serializers emitted UTC timestamp strings for direct SQL inserts. The fixture now uses naive UTC datetime attributes for database columns. The final full suite passes all 283 checks, including both regressions and the shared whole-task context field.

Beginner/experienced bands are synthetic internal fixtures, not persisted evidence or calibrated mastery. The public API only consumes stored authoritative unknown state today; the original initial-state database constraint is unchanged. Track A does not call a generator/provider, score work, update state or certify competency. Educational quality and university policy approval remain unverified. Day 7 downgrade loses plans/steps and is tested only in the disposable database.

## Day 6 — October 7, 2026

| Check | Measured result |
|---|---|
| `docker compose --profile test run --build --rm tests` | 231 passed; no skips; final run 6.28 seconds |
| Runtime/database | Python 3.9.21 image; MySQL 8.4 |
| Migration lifecycle and Alembic comparison | Upgrade/base downgrade; populated Day 5 snapshots survive 0006 downgrade/re-upgrade; no schema differences |
| Review/access | Author/instructor boundaries, own-author scope, self-review denial, attributed terminal review, stable retries and concurrent conflicting decisions |
| Selection/versioning | Three approved formats, four components; draft/rejected list/detail exclusion; exact approved policy IDs retained across new versions |
| Validation and rollback | Missing/unknown/relaxed rules rejected; version/duration/mapping bounds; failed mapping insertion and failed review leave no partial changes; MySQL constraints checked |
| Local migration | All eight existing table row hashes match after additive migration |
| `python3 scripts/demo_day6.py` | Live HTTP acceptance passed; retained synthetic run `_B3C50883` |
| `docker compose up --build -d --wait api` | Migration completed; application API/database healthy |

Preserved local rows: six courses, four domains, four competencies, thirteen skills, five prerequisite links, two learners, two enrollments and twelve skill states. Only counts/hashes were emitted for preservation comparison; no credentials or identity mappings were printed. Earlier migrations are unchanged.

The live demo created two approved policies, three approved activities with all four components, one draft policy, one draft activity and one rejected activity. Draft/rejected consumer reads returned 404, unauthorized reviews 403, content edits 405, changed terminal decisions 409, exact retries unchanged 200 representations, and unapproved policy references 404. Writes used APIs and existing synthetic credentials; course/learner content was not modified.

An initial run found a fixture packaging path error; the shared fixture now lives under the packaged application directory. Another run passed 221 checks and found a test expecting the wrong exception class for MySQL CHECK failures: PyMySQL reports error 3819 as OperationalError. The corrected test verifies the constraint error code. The final suite, including additional safety and failed-review regressions, passed all 231 checks.

Instructor-role approvals are automated synthetic workflow tests, not human expert review or university approval. All scope remains `synthetic_only`, with `provisional` activity evidence tiers. No planner, generator, scoring, runtime policy evaluator, real learner data or AI provider call is part of this milestone. University review and retirement/revocation remain required before rollout. Day 6 downgrade destroys catalog data and is tested only in the disposable database.

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
