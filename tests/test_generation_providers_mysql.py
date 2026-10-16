"""AI persistence uses the same review, isolation, replay and rollback boundaries."""
import json

import pytest
from sqlalchemy import func, select, update
from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.generation_providers import OPENAI_MODEL, OPENAI_GENERATOR_VERSION, PROMPT_VERSION, ProviderUnavailable, TemplateProvider
from app.models import Activity, ActivityGeneration
from tests.test_generation_providers import completion
from tests.test_plans_mysql import planning
from tests.test_catalog_mysql import policies
from tests.test_domains_mysql import create

pytestmark = pytest.mark.mysql


def enable(monkeypatch):
    monkeypatch.setenv("OPENAI_GENERATION_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "private-provider-key")
    get_settings.cache_clear()


def fake_transport(calls):
    def transport(body, key, timeout):
        calls.append(body)
        candidate = json.loads(body["input"])["reference_sequence"]
        candidate["steps"][0]["content"]["prompt"] = "AI synthetic wording. " + candidate["steps"][0]["content"]["prompt"]
        return completion(candidate)
    return transport


def install_transport(monkeypatch, transport):
    # Factory default is resolved at construction, so inject the actual HTTP boundary.
    from app.generation_providers import OpenAIProvider
    monkeypatch.setattr("app.activities.get_generation_provider",
        lambda name, settings, template_builder: OpenAIProvider(settings, transport) if name == "openai"
        else TemplateProvider(template_builder))


def test_ai_roundtrip_review_history_isolation_and_offline_retry(mysql_client, mysql_engine, role_headers, planning, monkeypatch):
    enable(monkeypatch); calls = []; install_transport(monkeypatch, fake_transport(calls))
    key = role_headers["learner"]; route, payload, _, ep, _ = planning
    plan, pp = create(mysql_client, key, route, payload)
    before = mysql_client.get(ep + "/state", headers=key).json()
    template, _ = create(mysql_client, key, pp + "/generations", {})
    ai, gp = create(mysql_client, key, pp + "/generations", {"provider": "openai"})
    assert ai["provider"] == "openai" and ai["model"] == OPENAI_MODEL
    assert ai["prompt_version"] == PROMPT_VERSION and ai["generator_version"] == OPENAI_GENERATOR_VERSION
    assert ai["id"] != template["id"] and ai["content_hash"] != template["content_hash"]
    assert ai["review_status"] == "draft" and len(calls) == 1
    assert mysql_client.post(pp + "/generations", headers=role_headers["learner2"], json={"provider": "openai"}).status_code == 404
    ap = "/api/v1/activities/" + ai["activities"][0]["id"]
    assert mysql_client.get(ap, headers=key).status_code == 404
    review = mysql_client.get(gp + "/review-content", headers=role_headers["instructor"])
    assert review.status_code == 200 and review.json()["candidate"]["generator_version"] == OPENAI_GENERATOR_VERSION
    approved = mysql_client.post(gp + "/review", headers=role_headers["instructor"], json={"decision": "approved", "note": "Synthetic AI test"})
    assert approved.status_code == 200
    monkeypatch.setenv("OPENAI_GENERATION_ENABLED", "false"); get_settings.cache_clear()
    retry = mysql_client.post(pp + "/generations", headers=key, json={"provider": "openai"})
    assert retry.status_code == 200 and retry.json() == approved.json() and len(calls) == 1
    assert mysql_client.get(ap, headers=key).status_code == 200
    assert mysql_client.get(gp + "/progress", headers=key).json()["status"] == "in_progress"
    history = mysql_client.get(pp + "/generations", headers=key).json()["items"]
    assert {g["provider"] for g in history} == {"template", "openai"}
    assert mysql_client.get(ep + "/state", headers=key).json() == before
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(ActivityGeneration)) == 2
    monkeypatch.setattr("app.database.get_engine", lambda: mysql_engine)
    with pytest.raises(RuntimeError, match="AI provenance"):
        command.downgrade(Config("alembic.ini"), "0011_continuity")
    command.check(Config("alembic.ini"))


@pytest.mark.parametrize("mode,status", [("disabled", 503), ("key_missing", 503), ("upstream", 503), ("invalid", 409)])
def test_provider_failure_writes_nothing(mysql_client, mysql_engine, role_headers, planning, monkeypatch, mode, status):
    enable(monkeypatch)
    if mode == "disabled": monkeypatch.setenv("OPENAI_GENERATION_ENABLED", "false")
    if mode == "key_missing": monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    calls = []
    def transport(body, *args):
        calls.append(body)
        if mode == "upstream": raise ProviderUnavailable("OpenAI generation unavailable or timed out")
        candidate = json.loads(body["input"])["reference_sequence"]
        candidate["steps"].reverse()
        return completion(candidate)
    install_transport(monkeypatch, transport)
    route, payload, _, _, _ = planning
    _, pp = create(mysql_client, role_headers["learner"], route, payload)
    reply = mysql_client.post(pp + "/generations", headers=role_headers["learner"], json={"provider": "openai"})
    assert reply.status_code == status, reply.text
    assert "private-provider-key" not in reply.text
    assert len(calls) == (0 if mode in {"disabled", "key_missing"} else 1)
    with mysql_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(ActivityGeneration)) == 0
        assert conn.scalar(select(func.count()).select_from(Activity)) == 0


def test_ai_provenance_corruption_is_withheld(mysql_client, mysql_engine, role_headers, planning, monkeypatch):
    enable(monkeypatch); install_transport(monkeypatch, fake_transport([]))
    route, payload, _, _, _ = planning
    _, pp = create(mysql_client, role_headers["learner"], route, payload)
    _, gp = create(mysql_client, role_headers["learner"], pp + "/generations", {"provider": "openai"})
    with mysql_engine.begin() as conn:
        conn.execute(update(ActivityGeneration).values(prompt_version="unrecorded"))
    assert mysql_client.get(gp + "/review-content", headers=role_headers["instructor"]).status_code == 409
    assert mysql_client.post(gp + "/review", headers=role_headers["instructor"], json={"decision": "approved", "note": "Corrupt"}).status_code == 409


def test_populated_day11_upgrade_preserves_template_content(mysql_client, mysql_engine, role_headers, planning, monkeypatch):
    route, payload, _, _, _ = planning
    _, pp = create(mysql_client, role_headers["learner"], route, payload)
    generation, gp = create(mysql_client, role_headers["learner"], pp + "/generations", {})
    before = mysql_client.get(gp + "/review-content", headers=role_headers["instructor"]).json()
    monkeypatch.setattr("app.database.get_engine", lambda: mysql_engine)
    config = Config("alembic.ini")
    command.downgrade(config, "0011_continuity")
    command.upgrade(config, "head")
    command.check(config)
    assert mysql_client.get(gp, headers=role_headers["learner"]).json() == generation
    assert mysql_client.get(gp + "/review-content", headers=role_headers["instructor"]).json() == before


def test_historical_prompt_v1_remains_reviewable(mysql_client, mysql_engine, role_headers, planning, monkeypatch):
    from app.generation_providers import OPENAI_V1_SPEC
    from app.generator import content_hash
    from app.generation_schemas import GeneratedSequence
    enable(monkeypatch)
    calls = []; install_transport(monkeypatch, fake_transport(calls))
    route, payload, _, _, _ = planning
    _, pp = create(mysql_client, role_headers["learner"], route, payload)
    generation, gp = create(mysql_client, role_headers["learner"], pp + "/generations", {"provider": "openai"})
    candidate = mysql_client.get(gp + "/review-content", headers=role_headers["instructor"]).json()["candidate"]
    candidate["generator_version"] = OPENAI_V1_SPEC.generator_version
    # Emulate retained v1 metadata; activity payloads are identical and remain frozen.
    with mysql_engine.begin() as conn:
        conn.execute(update(ActivityGeneration).where(ActivityGeneration.id == generation["id"]).values(
            generator_version=OPENAI_V1_SPEC.generator_version, prompt_version=OPENAI_V1_SPEC.prompt_version,
            content_hash=content_hash(GeneratedSequence(**candidate))))
    old = mysql_client.get(gp + "/review-content", headers=role_headers["instructor"])
    assert old.status_code == 200 and old.json()["candidate"] == candidate
    new, _ = create(mysql_client, role_headers["learner"], pp + "/generations", {"provider": "openai"})
    assert new["id"] != generation["id"] and new["prompt_version"] == PROMPT_VERSION
    assert len(calls) == 2
