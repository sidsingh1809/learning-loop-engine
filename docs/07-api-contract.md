# API contract conventions

Implemented contract, version 0.3.0. OpenAPI at `/openapi.json` is the route and schema reference. Application routes use `/api/v1`; health endpoints are unversioned and unauthenticated.

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

No domain deletion, cloning, prerequisite, or publishing endpoint is implemented. The schema reserves `published`, and authoring already rejects non-drafts; the publication transition and validation arrive on Day 4. Readiness checks all four implemented tables. Existing course endpoints retain their Day 2 behavior.
