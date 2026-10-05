# Identity and authorization integration design

## Implemented development principal

`Principal(subject, roles)` is an immutable, server-resolved identity. Known roles are `author`, `instructor`, `learner`, and `integration`. `API_KEY` maps to subject `dev-author` with the author role. Optional `DEV_PRINCIPALS` is a JSON array of `{subject, roles, api_key}` configured by the operator. The startup configuration rejects unknown or empty roles, short keys, duplicate keys and duplicate subjects, including the reserved primary subject.

Keys are compared in constant time per candidate and stored as secret-valued configuration. No role, subject or ownership supplied by a request body/header is trusted. Each additional author owns only their courses. Multiple role assignments are supported; permissions are additive. The old shared key now explicitly represents one local synthetic author, not multiple people.

| Role | Implemented course and domain access | Later responsibilities, not granted yet |
|---|---|---|
| Author | Read registry and domain metadata; create courses; edit/archive own courses; author own-course draft domains | Activity content; publishing under review policy |
| Instructor | Read registry and domain metadata | Assigned enrollments, review eligible constructed responses |
| Learner | Read registry/domain metadata; register self; create/read own enrollments and read own unknown state | Own plans, attempts and evidence-backed state updates |
| Integration | Read registry and domain metadata | Explicit service scopes and course/enrollment grants |

Archived course and domain metadata remains readable. Domain mutations require an active course owned by the author and a draft domain; IDs cannot cross course/version boundaries. Archival does not erase retained records. Day 5 adds synthetic learner data and self-enrollment permissions. No reviewer authority, administrator bypass, ownership transfer, instructor assignments or integration learner grants exist yet.

Day 5 registration derives an internal, case-sensitive subject mapping from the authenticated principal and returns a random learner UUID. Bodies cannot choose that subject or provide names/emails. This is pseudonymization, not anonymization: operators can still link the stored subject to the principal. Learners must own the requested UUID; sensitive missing/unauthorized learner and enrollment resources return 404. A learner cannot read or enroll another learner, including by placing another enrollment ID beneath their own learner path. Additional roles do not bypass ownership. A principal with learner and author roles may access their own learner records only.

## University adapter boundary

Replace development key resolution with an identity adapter that returns the same principal type, then keep resource authorization in service dependencies. Production must explicitly select the university adapter and disable development-key fallback. That deployment mode switch and the adapter are still future work; this version is local-only.

The proposed adapter validates signed access tokens against configured issuer, audience and permitted algorithms, enforces expiry and applicable not-before checks, and uses the university's approved key-discovery and rotation process. Unknown keys or unavailable validation must fail closed. Tokens and credentials must not enter application logs. This is an integration design, not implemented SSO or a security certification.

Map the verified `(issuer, subject)` pair to a stable internal principal ID rather than using email or display name. Map verified institution claims through an explicit allowlist into application roles. Service clients get separate identities and least-privilege scopes. Neither a learner ID in a URL nor a claimed course ID establishes access.

Before real identities replace development subjects, migrate course ownership through a reviewed mapping. Do not silently make a university author own all `dev-author` courses or leave these synthetic records accessible by default.

## Resource checks and remaining identity work

- Domain authoring inherits course ownership. Role alone never grants all-course mutation.
- Implemented Day 5: learner routes derive identity from the authenticated principal and scope both learner and enrollment lookup to it.
- Instructor access requires an explicit assignment to the relevant course/enrollment; an instructor role alone is insufficient.
- Integration clients need explicit operation scopes and resource grants; they cannot impersonate learners using request headers.
- Day 5 tests verify mutual learner denial, case-sensitive identity uniqueness, mismatched learner/enrollment and course/version parents, denied author/instructor/integration access and ignored spoofing headers. Instructor-assignment isolation still requires its own tests when those grants are introduced. Sensitive unauthorized learner/enrollment reads return 404.

University inputs still needed: identity provider and discovery details; access-token format, issuer and audience; approved role claims; service-client provisioning; instructor assignment source; identity mapping and retention policy; operational owners for key rotation and access revocation. These inputs do not block the synthetic course milestone.
