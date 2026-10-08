# Daily development plan

## Schedule and working method

Working assumption: one developer, 3–6 hours per working day. The user has already spent two hours today. Day numbers are work sessions, not calendar dates; no weekend work or automatic daily execution is assumed.

Aim for a synthetic closed-loop demo by Day 10 and an integration-ready prototype by Day 20. This is approximately 60–120 hours total, with the lower end allowing little rework. Days involving identity, generation, and integration can spill over. Re-estimate after Days 4, 10, and 15 based on actual progress. Research validation and production release have separate gates.

On a three-hour day, spend roughly 15 minutes choosing the acceptance test, two hours building, 30 minutes testing, and 15 minutes updating the log. On a longer day, finish the same acceptance criteria first, then pull the next dependency-ready task. Reserve testing and reporting time every day. Do not mark work done merely because code exists.

## Daily milestones

| Day | Portion and work | Demo or acceptance evidence | Daily update focus |
|---|---|---|---|
| 1 | Scope, source review, architecture, MySQL setup, Python 3.9.21 container, course create/read APIs | Fresh migration, authenticated course round trip, health, passing API/MySQL tests | Foundation implemented; adaptive loop still planned |
| 2 | Course edit/archive, API contract conventions, role/identity integration design, development principal model | Course edited and archived by authorized author; invalid role denied; no hard deletion of evidence-bearing content | Course lifecycle and access boundary |
| 3 | Domain version, competency, and skill migrations and authoring APIs | Create synthetic programming competency with five classified skills through APIs | Domain model can represent the pilot |
| 4 | Prerequisite edges, cycle detection, publish validation, immutable versions | Reject self/cross-version/cyclic edges; publish a complete graph; block edits to a published version | Validated prerequisite graph; revised estimate |
| 5 | Pseudonymous learners, enrollments, learner state reads, object-level permissions | Enroll two synthetic learners; unknown initial state; each learner denied access to the other's records | Learner model and isolation |
| 6 | Minimal activity library, 4C/ID mappings, versioned learning-science and safety policies | Approved worked example, selected response, and constructed response entries; unapproved content excluded | Reviewed catalog contract; university review still needed |
| 7 | Track A deterministic planner, prerequisite focus, rationale, support and time budget | Same fixture gives same explainable plan; beginner and experienced fixtures differ appropriately | Next-action decision API works independently |
| 8 | Track B template generator, plan-step ordering, rubric/content schemas | Plan becomes connected activity sequence; rejects invalid output; returns to whole task after support | Activity generation from a stored plan |
| 9 | Attempts, selected-response scoring, instructor review path, immutable evidence | Learner submits response, scorer records evidence; client-supplied authoritative score rejected | Evidence recording and scoring |
| 10 | Transactional state update, attempt idempotency, full loop integration | Attempt changes state and next plan; replay produces no extra evidence; whole-task progress remains explicit | First working loop, with provisional mastery policy |
| 11 | Resumption, generation history, context variation, experimental review schedule | Resume same sequence; distinct variants; due review appears without an invented mastery reset | Continuity across sessions |
| 12 | Generation provider interface, one AI provider/model using a server-side API key, prompt versions | Template and single-model adapters share contract; demonstrate generation from a synthetic learner's plan; disabled provider fails clearly | First AI integration; record chosen provider/model and actual API verification |
| 13 | Durable generation jobs, timeouts, bounded retries, idempotent generation requests | Provider failure and malformed output handled; retry does not publish duplicate activity | Reliable generation lifecycle |
| 14 | Evaluation set and review APIs with instructor feedback | Evaluate beginner, prerequisite-gap, experienced, short-window and unknown-state scenarios; track content/rubric quality | Findings and limits, not a claim of learning efficacy |
| 15 | External integration contract, signed callbacks/outbox or polling, client examples | Separate demo client drives complete loop; duplicate event handling verified | Integration demo and revised release estimate |
| 16 | University identity adapter if details available, role hardening, authorization matrix | Invalid issuer/audience/expiry/signature rejected; author/instructor/learner permissions checked | Identity integration; explicitly report unavailable SSO inputs |
| 17 | Audit trail, request IDs, structured logs, error metrics, rate limits | Trace plan→activity→attempt→state; no tokens or learner answers in logs; throttling test | Operational visibility and access protection |
| 18 | Database indexes, concurrency, migration CI, bounded load tests | Simultaneous attempts preserve evidence and state; migration from previous version passes; measured latency at agreed load | Reliability evidence and remaining bottlenecks |
| 19 | Staging configuration, deployment, backup/restore, rollback and secret rotation runbooks | Restore synthetic data to a clean environment; deployment health and rollback rehearsal | Deployment readiness; actual deployment depends on chosen host |
| 20 | End-to-end acceptance, documentation, integration handover, prioritized pilot backlog | Demo repeated from clean setup; test/evaluation report; unresolved gates listed | Prototype handover and next release decision |

Days 1–7 are implemented and verified; see `verification.md` for measured results and `13-day-7.md` for the current walkthrough. Catalog review is an instructor-role engineering workflow for synthetic use; substantive expert and university review remain outstanding. Day 8 template generation from saved plans is the next implementation session. Later learning features remain planned.

Day 4 estimate review (October 3, 2026): the planned graph/publication milestone is complete without pulling later learner or AI work forward. Keep the engineering prototype target at Day 20: 16 working sessions remain, approximately 48–96 hours at the existing 3–6 hours/session assumption. This is a planning estimate, not measured effort or a production release date. Re-estimate at Day 10 after the learner/evidence loop is verified; university identity, provider selection and review inputs remain unresolved.

Product direction confirmed October 2, 2026: personalize each student's course experience from prior knowledge and subsequent evidence. Begin with one AI model to understand the entire process; add other models and compare them later. Days 3–4 supply the shared skill structure, Days 5–10 establish learner state and the adaptive loop, and Days 12–13 add the first model integration and durable execution. Provider/model selection remains open. See `01-scope.md` for the recorded decision.

## Day 1 remaining personal work

With two hours already spent today, budget another 1–2 hours to review the design, run the example, and prepare the update. A longer day is optional.

1. 15–20 minutes: read scope and understand the difference between a planner and a generator.
2. 20–30 minutes: inspect the running API docs and execute the course API example.
3. 20–30 minutes: follow request schema → route → database session → model → response in code.
4. 10–15 minutes: run the test command and read the Day 1 update.
5. Remaining time: prepare the five pilot skill descriptions for Day 3. Do not invent university-approved mastery thresholds.

## Prototype acceptance scenarios

- Beginner: unknown evidence causes diagnostic/guided work rather than an unsupported low-mastery claim.
- Missing prerequisite: a prerequisite gap changes the next focus and retains the connection to the original whole task.
- Experienced learner: valid prior evidence reduces support or increases complexity under the configured policy.
- Short session: selected sequence fits the stated budget or explains that no appropriate task fits.
- Repeated attempt: new context can be offered, but an HTTP retry never adds a second evidence record.
- Interrupted session: a learner resumes their current progress without losing previous attempts.
- Whole-task evidence: part-task success alone cannot automatically certify a professional competency.
- Provider or database failure: no partially published activity and no partially applied mastery update.
- Authorization: learners cannot fetch another learner's data or author an authoritative score.

## Work after the engineering prototype

| Stage | Necessary work | Exit gate |
|---|---|---|
| University pilot preparation | Replace synthetic graph/content with reviewed CTA and rubrics; choose formal assessment boundaries; review privacy, retention, safety and accessibility | Named university owners approve pilot inputs and operating policy |
| Research validation | Compare planner recommendations with experts; evaluate connected activity quality, calibration and learning outcomes; study spacing and support policies | Evidence supports the defined use, with measured uncertainty and documented failure cases |
| Production hardening | Resolve Python lifecycle requirement, complete security and dependency reviews, set load/availability targets, run recovery drills, monitor cost | Approved release checklist, operational owner, rollback plan and support process |
| Controlled rollout | Small authorized cohort, monitoring and human escalation, gradual expansion | Success criteria met before adding courses or learners |
| Later features | Full contextual coaching, mentor alerts, richer simulations, sandboxed code execution, multiple course graphs | Separate scoped and evaluated releases |

Do not promise a production date until the responsible owners, infrastructure, evaluation criteria, and review availability are known.
