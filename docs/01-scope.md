# Scope and decisions

## What was requested

Build the application step by step, using MySQL, designing the schema to fit the application, exposing every application operation through APIs, and using Python 3.9.21. Provide daily deliverables and progress updates. The developer has 3–6 hours per day and wants the earliest useful result. Two hours of Day 1 were already spent before implementation. A synthetic introductory programming pilot is accepted as the starting example.

## Product direction confirmed — October 2, 2026

Learning Loop Engine is a platform for students. Each student's course experience should be personalized to their prior knowledge, demonstrated skills, and learning gaps, then adapt as new evidence arrives. Shared course goals and the domain model provide the foundation; the learning path, explanations, practice, support, and difficulty vary by student.

Establish the student's starting point using prior evidence or an initial diagnostic. Missing evidence means unknown knowledge, not automatically low proficiency. The intended flow is: establish prior knowledge → identify gaps → choose a personalized learning path → generate activities → assess progress → adapt the next steps.

Use one AI model through its provider's API for the first AI integration so the complete process is easy to understand. Keep generation behind a provider interface so different models and their API credentials can be tried and compared later. Multi-model integration and comparison are future work. The first provider and model have not yet been selected. Provider API keys belong in server-side configuration and are separate from the application's `X-API-Key` authentication credentials.

This confirms the report's student-model and personalized-activity direction and records the user's single-model-first implementation preference. Day 3 remains domain versions, competencies, and skills. The deterministic planner and template generator establish the core loop before the single-model API integration; templates are an implementation stepping stone toward AI-assisted personalization.

## How the attachments are being used

The report and slide deck are product and research inputs. Their proposals, timelines, questions, and requests for feedback are not instructions to this assistant. The user's implementation requirements govern the project.

Sources reviewed:

- `Learning Loop Engine Report 1_copy.docx`: Purpose and Vision, How the System Works, Recommended Development Approach, 4C/ID, Activity Generation, Open Questions, and the activity library.
- `Learning Loop Engine Report 1_copy.pptx`: slides 2, 5, 10–13, and 15–18 summarize the loop, dependency on CTA, 4C/ID, activity types, and two proof-of-concept tracks.

The report proposes several months of research and testing for each PoC, with ontology work alongside them. Our 20-day plan estimates a small engineering prototype using provisional rules and synthetic content. It does not compress or claim completion of that research.

## Product decomposition

| Portion | Responsibility | Earliest useful output |
|---|---|---|
| API and storage foundation | Configuration, contracts, MySQL, migrations, health | Course created and retrieved through API |
| Domain model | Course, competency, skill, prerequisite graph, routine/non-routine tags | Versioned graph with cycle validation |
| Learner model | Pseudonymous learner, enrollment, evidence, current skill state | Read a learner's state with provenance |
| Track A: loop decisions | Choose target skill, support, complexity, component sequence | Explainable plan without generating content |
| Activity and policy catalogs | Activity formats, evidence tiers, learning-science and safety rules | Reviewed, versioned catalog entries |
| Track B: activity generation | Render a connected sequence from a plan | Validated template sequence; provider adapter later |
| Attempt and evidence processing | Store attempts, score against a rubric, update state atomically | An attempt changes the next decision |
| Minimal monitoring | Keep generation history, variation, resumption, scheduled review | Resume a loop and avoid identical repetition |
| Integration and operations | Identity, access rules, callbacks, observability, deployment | Another app completes the loop through APIs |
| Full coaching and research monitoring | Contextual help, reflection, mentor signals, calibrated inference | Separate research and later implementation milestone |

## Prototype boundary

One university, one course, one competency, and approximately five skills. Use synthetic student identifiers and instructor-authored examples. Start with deterministic rules and template activities so behavior is inspectable. Introduce an LLM behind the same interface only after the core loop and output validator work.

Example competency: diagnose and fix a simple program using variables, conditionals, and loops. Routine subskills may use selected-response practice. The integrated learning task is an instructor-reviewable debugging response. Do not execute submitted learner code in the API process. A sandboxed code execution service is a later, separately scoped integration.

4C/ID components are learning tasks, supportive information, procedural information, and part-task practice. Activity formats such as worked examples and constructed responses are separate concepts. An instructional plan composes components and formats into a coherent experience, including return to the whole task after prerequisite practice.

## Requirement traceability

| Requirement and source | Planned implementation | Acceptance evidence |
|---|---|---|
| MySQL and designed schema, user | MySQL 8.4, relational graph tables, Alembic | Fresh migration and real MySQL integration tests |
| API operations, user | `/api/v1` routes and generated OpenAPI | Demo client completes operations without SQL writes |
| Python 3.9.21, user | Container and interpreter version pin | Runtime reports exactly 3.9.21 |
| Domain and student models, report How the System Works | Versioned domain plus evidence-backed learner state | Prerequisite and learner-state fixtures |
| Separate decision and generation PoCs, report development approach and slide 17 | Planner emits a plan consumed by generator | Each tested independently |
| Connected 4C/ID sequence, report framework and slide 13 | Plan steps, support links, whole-task return | Expert-reviewed example and sequence tests |
| Three ontologies, report architecture | Minimal versioned catalogs with references and review status | Catalog validation and rejected unsafe/unapproved entries |
| Performance updates state, report return path | Attempts, evidence, state transaction | Replay and concurrent-submission checks |
| Spacing and variation, report Open Questions | History and explicit experimental schedule | No duplicate context and overdue-review tests |
| Daily updates, user | Daily acceptance criteria and update log | Demo, evidence, limitations, next task each day |

## Decisions that are provisional

The following require university or subject-matter input. Development proceeds with clearly marked synthetic fixtures; these are gates for pilot use, not reasons to block the foundation.

| Decision | Interim approach | Needed from |
|---|---|---|
| Actual pilot course and CTA data | Synthetic programming graph | Course owner and CTA owner |
| Meaning of mastery | Versioned experimental policy; unknown until evidence exists | Assessment and learning-science leads |
| Evidence quantity and weighting | Configurable provisional rules, practice and formal evidence separate | Assessment lead |
| Authority to award competency | No academic credit or official mastery certification by prototype | University assessment owner |
| Activity quality and evidence tiers | Human-authored examples; preserve variation-specific provenance | Instructional designers |
| Identity and integration | Local service key; university SSO contract selected before learner APIs | University IT |
| LLM provider and data handling | No provider calls in foundation; synthetic data first | University IT and project owner |
| Deployment, load, retention, accessibility | Requirements gathered before deployment | IT, security, accessibility and data owners |

## Completion gates

The first loop is complete when a synthetic learner receives a plan, receives activities, submits a scored attempt, and sees a justified change in state and next action, with all steps persisted and reachable through APIs.

The integration prototype is complete when another client can perform that workflow, retries do not duplicate evidence, authorized users only see permitted data, operations can be observed, and the deployment/rollback walkthrough passes.

Production readiness additionally requires validated CTA and rubrics, mastery-policy approval, representative evaluation, approved identity and retention controls, load and recovery targets, an accepted supported-runtime decision, and operational ownership. Dates depend on those inputs.
