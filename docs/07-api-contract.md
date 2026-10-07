# API contract conventions

Implemented contract, version 0.6.0. OpenAPI at `/openapi.json` is the route and schema reference. Application routes use `/api/v1`; health endpoints are unversioned and unauthenticated.

## Representation and validation

- JSON request and response bodies; UUID identifiers; UTC timestamps ending in `Z`. MySQL timestamps currently have second precision and must not be used as concurrency tokens.
- Course codes are trimmed, uppercase ASCII identifiers, at most 32 characters. Titles are trimmed and nonempty, at most 200 characters; descriptions are trimmed and at most 10,000 characters.
- Unknown request fields are rejected. Ownership, timestamps and status are server controlled.
- PATCH accepts any nonempty subset of `code`, `title`, `description`. Omitted values are unchanged, explicit null is rejected, and an empty description clears it. Empty patches return 422.
- Every course representation includes `id`, `code`, `title`, `description`, `created_at`, `created_by`, `updated_at`, `archived_at`, `status`. Status derives from the archive timestamp.
- Lists return `{items, limit, offset}` ordered by unique code. Default limit 20, maximum 100, nonnegative offset. `status=active` is the default; `archived` and `all` are supported. Filtering precedes pagination. No total count or snapshot consistency is promised.

## HTTP behavior

| Operation or outcome | Status and behavior |
|---|---|
| Course creation | 201 with representation and relative `Location` header |
| Read, edit, archive | 200 with persisted representation |
| Missing/invalid key | 401 |
| Authenticated caller lacks author role or course ownership | 403 |
| Unknown course UUID | 404 |
| Unsupported method, including DELETE on an existing course route | 405 |
| Duplicate normalized code, including an archived code; edit after archive | 409 |
| Invalid UUID, query or body | 422 |
| Database operation unavailable | Sanitized 503 |

Errors use FastAPI's `{"detail": ...}` envelope: a string for application/authentication/database errors, a validation-error array for request-schema 422 errors, or a string for the skill PATCH resulting-state 422 check. Clients should branch on status codes and validation locations, not parse message prose. Database failures never expose SQL or credentials.

All four development roles may read registry metadata, including archived courses. Only an author may create. Only the creating author may edit or archive a course. An author querying an unknown ID gets 404; a non-author attempting writes gets 403 before record lookup. This registry policy does not grant access to future learner records.

## Lifecycle, retries and transactions

Courses start active. Archival retains the row and unique code; it is terminal in this milestone. No restore, transfer-ownership or hard-delete route is implemented. Repeating archive returns the same stored timestamps. Codes may be changed while active; integrations must refer to stable UUIDs, not mutable codes.

PATCH and archive lock the same course row. A concurrent edit either completes before archival or sees the archived state and returns 409. Concurrent edits to the same field use the last successful write; no ETag or revision check is implemented. Duplicate-code failure rolls the entire edit back. A no-op PATCH may leave `updated_at` unchanged.

Creation does not implement idempotency keys: a repeat with the same code returns 409. Archive is idempotent. GET is safe to retry. Attempt and generation idempotency remains planned for the milestones that introduce those resources.

The default list now excludes archived courses; clients needing history must request `status=all`. Existing courses migrate to active and preserve their UUIDs, codes, descriptions and creation times. New response fields are additive.


## Day 3 domain authoring

All routes are nested under `/api/v1/courses/{course_id}/domain-versions`:

| Relative route | Methods | Behavior |
|---|---|---|
| Collection | POST, GET | Create an empty draft with `{}`; list versions |
| `/{domain_version_id}` | GET | Read version within this course |
| `/{domain_version_id}/competencies` | POST, GET | Create/list competencies |
| `/{domain_version_id}/competencies/{competency_id}` | GET, PATCH | Read/edit competency within this version |
| `/{domain_version_id}/skills` | POST, GET | Create/list classified skills |
| `/{domain_version_id}/skills/{skill_id}` | GET, PATCH | Read/edit skill within this version |

Creation returns 201 with a relative `Location` and the persisted representation; reads/edits return 200. All lists return `{items, limit, offset}`, with default limit 20, maximum 100 and nonnegative offset. Versions sort by ascending version number, competencies/skills by code. Parents are checked before listing: an unknown or mismatched parent returns 404, while an existing empty collection returns an empty page.

Domain version numbers are server allocated, unique and sequential within a course. Each creation makes an empty draft; it does not clone an older version. POST retries create another version because idempotency keys are not implemented. Clients should inspect the version list after an uncertain response before retrying. Status, parent ownership and timestamps are server controlled.

Competency creation requires `code` and `statement` (trimmed, 1–10,000 characters). Skill creation requires `competency_id`, `code`, `title`, and `skill_kind`; description defaults to empty, `requires_automaticity` defaults to false and accepts only JSON booleans. Code, title and description follow the course length/normalization rules. `skill_kind` is `routine` or `non_routine`; automaticity can be true only for routine skills. This is a provisional authoring convention, not a student proficiency judgment.

Competency PATCH accepts code/statement; skill PATCH accepts code/title/description/kind/automaticity. Omitted fields remain unchanged, explicit null/empty patches return 422, and parent IDs cannot be edited. Skill PATCH validates the resulting kind/automaticity pair, so switching a routine skill with automaticity to non-routine must also set automaticity to false. Competencies and skills return UTC creation/update timestamps.

Codes are unique per domain version within each resource type; skill codes remain unique across competencies in that version. Duplicate creation or edits return 409 and roll back the entire write. The same codes may be used in another version. A skill's competency must exist in the requested version: missing or cross-version references return 404, and a composite database FK enforces the same boundary.

All four development roles may read this synthetic domain metadata, including drafts and archived-course domains. Writes require the author role and course ownership (403 otherwise), an active course, and a draft domain (409 otherwise). Missing or mismatched nested resources return 404. Authoring locks the course before the domain, serializing it with archival. Concurrent creation allocates distinct version numbers. Edits use last successful write semantics; no ETag or revision precondition exists yet.

No domain deletion or cloning endpoint is implemented. Day 4 adds the graph and publication operations below. Readiness checks all eleven implemented tables, including publication, learner and catalog metadata. Existing course endpoints retain their Day 2 behavior.

## Day 4 prerequisites, validation and publishing

Under the same version path:

| Relative route | Methods | Behavior |
|---|---|---|
| `/prerequisites` | POST, GET | Create a draft prerequisite link; list links |
| `/prerequisites/{prerequisite_id}` | GET, DELETE | Read a link; remove a draft link |
| `/validate` | POST | Read-only validation report; body `{}` |
| `/publish` | POST | Validate and publish a complete draft; body `{}` |

Prerequisite POST requires `skill_id` and `prerequisite_skill_id`: the first requires the second. Self-links return request-schema 422. Missing or foreign-version endpoints return 404. Duplicate edges and edges creating any cycle return 409. Creation returns 201 with a relative `Location`, UUID and UTC creation timestamp. Lists use standard pagination, ordered by `(skill_id, prerequisite_skill_id)`. Draft-link DELETE returns 204 with no body; a missing link returns 404. Link endpoints cannot be patched; remove and recreate the draft link to correct it.

Validation requires at least one competency and skill, a skill for every competency, correct skill classifications and same-version references, and an acyclic graph. Multiple roots and independent skills are allowed; descriptions may be empty. It reads the full graph, independent of collection pagination. POST `/validate` returns 200 with `{domain_version_id, valid, issues, topological_skill_ids}`. Each issue has a stable `code`, explanatory `message`, and `resource_ids`. Supported codes are `no_competencies`, `no_skills`, `empty_competencies`, `invalid_skills`, and `invalid_graph`. Invalid reports contain an empty order. Valid reports order skills prerequisite-first with ties broken by code; this is not a personalized learning plan.

All metadata readers may validate drafts or published versions, including on archived courses. Validation acquires course then domain locks to produce a coherent report without changing content. Publishing requires course ownership and an active course. Invalid publication returns 422 with the same report in `detail` and leaves the draft unchanged. Successful publication returns 200 with the persisted domain representation: `status: published` and server-controlled UTC `published_at`. Draft representations contain `published_at: null`. Status/timestamp commit atomically.

Every competency/skill/link mutation rejects a published version with 409. Graph edits and publication use the same course-then-domain lock order as earlier authoring and archival. Opposing concurrent edges cannot both commit; an edit racing publication completes before validation or receives 409. A repeated publish on an active course returns the existing version and timestamp. After archival even repeated publish returns 409; reads and validation remain available. To revise content, create and author a new empty draft.

MySQL constraints enforce same-version endpoints, unique links, no self-link, and publication status/timestamp consistency. Cycles and immutable content are enforced by API services; direct operator SQL can bypass those service invariants. Publication always revalidates draft content.

## Day 5 learners, enrollments and state

All routes require the learner role. Non-learner roles receive 403 before object lookup. Every requested learner is resolved against the authenticated principal subject; another learner's UUID returns the same 404 as a missing learner. Enrollment lookup additionally checks its learner parent. Spoofed subject, role or learner headers never establish access. Authors do not gain access to learners through course ownership; instructor assignments and service grants remain unimplemented.

| Route under `/api/v1` | Method | Behavior |
|---|---|---|
| `/learners` | POST | Body `{}`; register authenticated principal only |
| `/learners/{learner_id}` | GET | Own pseudonymous UUID and UTC creation time |
| `/learners/{learner_id}/enrollments` | POST | Body `{course_id, domain_version_id}` |
| `/learners/{learner_id}/enrollments` | GET | Own enrollments, ordered by `(created_at, id)` |
| `/learners/{learner_id}/enrollments/{enrollment_id}` | GET | Enrollment belonging to this learner |
| `/learners/{learner_id}/enrollments/{enrollment_id}/state` | GET | Skill states for this enrollment, ordered by skill code |

First registration/enrollment returns 201 with Location; retries return 200 with the same persisted representation and Location. Registration accepts no identity fields. Enrollment requires an active course and a published version belonging to it (409 for archived/draft, 404 for missing/mismatched parents). One retained enrollment per learner/course is allowed; requesting a different published version returns 409. Enrollment version and status cannot be changed. After course archival existing records remain readable, but enrollment POST, including repeats, returns 409.

Enrollment creation commits its record and all initial skill states together. Each state contains `skill_id`, `domain_version_id`, `band: unknown`, `evidence_count: 0`, `revision: 0`, and UTC `updated_at`. The timestamp records initial persistence, not learning evidence. Unknown does not assert low proficiency. Retrying enrollment or reading state never resets or adds states. No client score, proficiency or state-update route exists. Evidence-backed changes come in Days 9–10.

Enrollment lists follow standard `{items, limit, offset}` pagination. State reads return `{enrollment_id, domain_version_id, items, limit, offset}`, default limit 20 and maximum 100. There is no learner directory or global enrollment list. All reads retain the standard sanitized database-error response.

## Day 6 versioned activity and policy catalog

All twelve operations below require authentication. Catalogs are global synthetic metadata and do not grant learner-data access.

| Route under `/api/v1/catalog` | Methods | Access and behavior |
|---|---|---|
| `/policy-versions`, `/activity-versions` | POST | Author creates immutable draft; 201, Location |
| `/policy-versions`, `/activity-versions` | GET | Authors list own submissions; instructors list all |
| `/policy-versions/{version_id}`, `/activity-versions/{version_id}` | GET | Same author/instructor scope; inaccessible UUID returns 404 |
| `/policy-versions/{version_id}/review`, `/activity-versions/{version_id}/review` | POST | Different instructor approves/rejects synthetic use; 200 |
| `/policies`, `/activities` | GET | Every authenticated role; approved versions only |
| `/policies/{version_id}`, `/activities/{version_id}` | GET | Every authenticated role; draft/rejected/missing UUID returns 404 |

POST schemas require normalized code, explicit version (strict integer 1–2,147,483,647), title and nonempty bounded references. Policy creation adds category and complete typed rules; missing/extra rules, category mismatches and relaxed boundaries return 422. Activity creation adds format, purpose, guidance, nominal minutes (strict integer 1–180), exact approved learning-science/safety policy UUIDs and one to four unique component mappings with rationale. Missing/unapproved policies return 404, wrong categories 422. Mappings and metadata commit atomically. Review status/scope/attribution and provisional evidence tier are server-controlled; caller-supplied values return 422.

Activity `(code, version)` and policy `(category, code, version)` are unique; duplicate creates return 409. Authors may contribute new versions to shared code families with per-version provenance. Content and mappings are immutable even in draft; PATCH/DELETE are unavailable (405). New versions never change existing bindings. Lists retain all approved versions; clients explicitly choose UUIDs rather than assuming latest or automatic supersession. Creation has no idempotency key.

Review body is `{decision: approved|rejected, note: nonempty text}`. Non-instructors and same-subject self-review receive 403. Server stores reviewer, UTC time, note and `synthetic_only` scope atomically. An exact decision/note retry by the same reviewer returns the original representation; changed terminal reviews return 409. Concurrent reviews serialize. Rejected versions cannot be resubmitted; create a new version. Expert/university review and retirement/revocation remain outside this milestone.

Lists return `{items, limit, offset}`, with standard bounds, ordered by `(code, version, id)`. Approved activity filters are `activity_type` and `component` (AND); policy filters use `category`. Authoring lists support `status`, with additional `category` for policies. Authors cannot inspect another author's submissions; instructors see all. Learner/integration roles receive 403 on authoring URLs. Extra consumer query parameters never expose unapproved content. See `12-day-6.md` and OpenAPI for complete schemas. Delivered prompts, answers, scoring and policy execution are later milestones.
