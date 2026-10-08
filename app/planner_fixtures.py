"""Synthetic internal evidence fixtures; never write these bands to live learners."""
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.planner_schemas import PlannerInput


def synthetic_input(profile="unknown", time_budget_minutes=25):
    root = Path(__file__).resolve().parent
    fixture = json.loads((root / "synthetic_planner.json").read_text())
    catalog = json.loads((root / "synthetic_catalog.json").read_text())

    def uid(code):
        return str(uuid5(NAMESPACE_URL, "learning-loop/synthetic/day7/" + code))

    review = {"created_by": "fixture-author", "created_at": "2026-10-08T00:00:00Z", "review_status": "approved",
              "review_scope": "synthetic_only", "reviewed_by": "fixture-instructor", "reviewed_at": "2026-10-08T00:00:00Z",
              "review_note": "Synthetic fixture only; no expert or university approval claimed."}
    policies = {p["category"]: {**p, **review, "id": uid(p["code"])} for p in catalog["policies"]}
    activities = [{**a, **review, "id": uid(a["code"]), "evidence_tier": "provisional",
                   "learning_science_policy_id": policies["learning_science"]["id"], "safety_policy_id": policies["safety"]["id"]}
                  for a in catalog["activities"]]
    return PlannerInput(domain_version_id=uid("DOMAIN"), target_skill_id=uid(fixture["target"]),
                        time_budget_minutes=time_budget_minutes,
                        skills=[{**s, "id": uid(s["code"])} for s in fixture["skills"]],
                        edges=[(uid(s), uid(p)) for s, p in fixture["edges"]],
                        states=[{"skill_id": uid(code), "band": band, "evidence_count": 0 if band == "unknown" else 2,
                                 "revision": 0 if band == "unknown" else 1} for code, band in fixture["profiles"][profile].items()],
                        learning_science_policy=policies["learning_science"], safety_policy=policies["safety"], activities=activities)
