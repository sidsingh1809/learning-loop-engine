"""Iterative graph checks for course-scoped domain authoring and publishing."""
from heapq import heapify, heappop, heappush

from sqlalchemy import select

from app.models import Competency, Skill, SkillPrerequisite


def topological_order(skills, edges):
    """Return prerequisite-first IDs, or None for a cycle/foreign endpoint.

    Code ordering breaks ties deterministically; no recursion-depth limit applies.
    """
    codes = {skill.id: skill.code for skill in skills}
    incoming = {skill_id: 0 for skill_id in codes}
    dependents = {skill_id: set() for skill_id in codes}
    for skill_id, prerequisite_id in edges:
        if skill_id not in codes or prerequisite_id not in codes:
            return None
        if skill_id not in dependents[prerequisite_id]:
            dependents[prerequisite_id].add(skill_id)
            incoming[skill_id] += 1
    ready = [(codes[skill_id], skill_id) for skill_id, count in incoming.items() if count == 0]
    heapify(ready)
    ordered = []
    while ready:
        _, skill_id = heappop(ready)
        ordered.append(skill_id)
        for dependent in dependents[skill_id]:
            incoming[dependent] -= 1
            if incoming[dependent] == 0:
                heappush(ready, (codes[dependent], dependent))
    return ordered if len(ordered) == len(codes) else None


def load_graph(domain_version_id, session):
    skills = session.scalars(select(Skill).where(Skill.domain_version_id == str(domain_version_id))
                             .order_by(Skill.code)).all()
    edges = session.execute(select(SkillPrerequisite.skill_id, SkillPrerequisite.prerequisite_skill_id)
                            .where(SkillPrerequisite.domain_version_id == str(domain_version_id))).all()
    return skills, edges


def validate_domain(domain_version_id, session):
    competencies = session.scalars(select(Competency).where(Competency.domain_version_id == str(domain_version_id))
                                   .order_by(Competency.code)).all()
    skills, edges = load_graph(domain_version_id, session)
    issues = []

    def issue(code, message, ids):
        issues.append({"code": code, "message": message, "resource_ids": ids})

    if not competencies:
        issue("no_competencies", "Add at least one competency before publishing", [])
    if not skills:
        issue("no_skills", "Add at least one skill before publishing", [])
    populated = {skill.competency_id for skill in skills}
    empty = [item.id for item in competencies if item.id not in populated]
    if empty:
        issue("empty_competencies", "Every competency must contain at least one skill", empty)
    competency_ids = {item.id for item in competencies}
    invalid = [skill.id for skill in skills if skill.competency_id not in competency_ids
               or skill.skill_kind not in ("routine", "non_routine")
               or (skill.skill_kind != "routine" and skill.requires_automaticity)]
    if invalid:
        issue("invalid_skills", "Skills must have a same-version competency and valid classification", invalid)
    order = topological_order(skills, edges)
    if order is None:
        issue("invalid_graph", "Prerequisites must be an acyclic graph of skills in this version", [])
    return {"domain_version_id": str(domain_version_id), "valid": not issues, "issues": issues,
            "topological_skill_ids": order if not issues else []}
