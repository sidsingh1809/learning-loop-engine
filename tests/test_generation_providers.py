"""Provider contracts and real HTTP serialization with an intercepted transport."""
from io import BytesIO
import json
from urllib.error import HTTPError, URLError

import pytest

from app.config import Settings
from app.generation_providers import (MAX_RESPONSE_BYTES, OPENAI_MODEL, OPENAI_GENERATOR_VERSION,
    PROMPT_VERSION, OpenAIProvider, ProviderUnavailable, TemplateProvider, get_generation_provider,
    post_response, response_body)
from app.generator import GenerationError, build_sequence, content_hash
from app.planner import build_plan
from app.planner_fixtures import synthetic_input


def settings(**overrides):
    return Settings(database_url="mysql+pymysql://test:test@localhost/test", api_key="x" * 32,
                    openai_generation_enabled=True, openai_api_key="private-provider-key",
                    _env_file=None, **overrides)


def completion(candidate):
    return {"status": "completed", "model": OPENAI_MODEL, "output": [{"type": "message",
        "content": [{"type": "output_text", "text": json.dumps(candidate)}]}]}


def ai_candidate(snapshot, plan, context="positive-sales-v1"):
    raw = build_sequence(snapshot, plan, context).model_dump(mode="json")
    raw["generator_version"] = OPENAI_GENERATOR_VERSION
    raw["steps"][0]["content"]["prompt"] = "Generated synthetic wording. " + raw["steps"][0]["content"]["prompt"]
    return raw


@pytest.mark.parametrize("profile", ["unknown", "beginner", "experienced"])
@pytest.mark.parametrize("context", ["positive-sales-v1", "positive-donations-v1"])
def test_shared_contract_preserves_plan_and_template_hash(profile, context):
    snapshot = synthetic_input(profile); plan = build_plan(snapshot)
    original = build_sequence(snapshot, plan, context)
    assert TemplateProvider().generate(snapshot, plan, context) == original
    assert content_hash(TemplateProvider().generate(snapshot, plan, context)) == content_hash(original)
    calls = []
    def transport(body, key, timeout):
        calls.append(body)
        return completion(ai_candidate(snapshot, plan, context))
    generated = OpenAIProvider(settings(), transport).generate(snapshot, plan, context)
    assert generated.generator_version == OPENAI_GENERATOR_VERSION
    assert generated.plan_fingerprint == original.plan_fingerprint
    assert [s.role for s in generated.steps] == [s.role for s in original.steps]
    assert generated.estimated_minutes == plan.estimated_minutes
    assert len(calls) == 1 and calls[0]["model"] == OPENAI_MODEL


@pytest.mark.parametrize("enabled,key,message", [(False, "key", "disabled"), (True, None, "OPENAI_API_KEY"), (True, " ", "OPENAI_API_KEY")])
def test_disabled_or_missing_key_never_calls_provider(enabled, key, message):
    config = settings().model_copy(update={"openai_generation_enabled": enabled, "openai_api_key": None})
    if key is not None:
        from pydantic import SecretStr
        config.openai_api_key = SecretStr(key)
    snapshot = synthetic_input(); plan = build_plan(snapshot)
    def forbidden(*args):
        pytest.fail("Disabled/misconfigured provider called the network")
    with pytest.raises(ProviderUnavailable, match=message):
        OpenAIProvider(config, forbidden).generate(snapshot, plan, "positive-sales-v1")
    assert TemplateProvider().generate(snapshot, plan, "positive-sales-v1")


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(status="incomplete"),
    lambda x: x.update(model="other"),
    lambda x: x.update(output=[]),
    lambda x: x.update(output=[{"type": "message", "content": [{"type": "refusal", "refusal": "private"}]}]),
    lambda x: x["output"][0]["content"][0].update(text="not json"),
    lambda x: x.update(output=None),
])
def test_incomplete_refused_and_malformed_output_rejected(mutation):
    snapshot = synthetic_input(); plan = build_plan(snapshot)
    response = completion(ai_candidate(snapshot, plan)); mutation(response)
    with pytest.raises(GenerationError):
        OpenAIProvider(settings(), lambda *args: response).generate(snapshot, plan, "positive-sales-v1")


@pytest.mark.parametrize("mutation", [
    lambda x: x["steps"].reverse(),
    lambda x: x.update(plan_fingerprint="0" * 64),
    lambda x: x.update(generator_version="track-b-template-v1"),
    lambda x: x["steps"][0].update(support_level="minimal"),
    lambda x: x["steps"][-1]["rubric"].update(formal_certification=True),
    lambda x: x["steps"][1]["content"].update(correct_choice_id="missing"),
])
def test_ai_cannot_override_plan_or_answer_schema(mutation):
    snapshot = synthetic_input("beginner"); plan = build_plan(snapshot)
    raw = ai_candidate(snapshot, plan); mutation(raw)
    with pytest.raises(GenerationError):
        OpenAIProvider(settings(), lambda *args: completion(raw)).generate(snapshot, plan, "positive-sales-v1")


def test_prompt_version_schema_and_minimized_context():
    snapshot = synthetic_input(); plan = build_plan(snapshot)
    body = response_body(snapshot, plan, "positive-sales-v1")
    assert PROMPT_VERSION in body["instructions"]
    assert body["store"] is False
    assert "private-provider-key" not in json.dumps(body)
    assert set(json.loads(body["input"])) == {"reference_sequence", "learner_skill_bands", "skills", "plan", "learning_science_rules", "safety_rules"}
    def walk(value):
        if isinstance(value, dict):
            assert not {"oneOf", "discriminator", "default", "const"} & value.keys()
            if value.get("type") == "object":
                assert value["additionalProperties"] is False
                assert set(value["required"]) == set(value["properties"])
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(body["text"]["format"]["schema"])
    assert get_generation_provider("template", settings()).spec.provider == "template"
    assert get_generation_provider("openai", settings()).spec.model == OPENAI_MODEL
    with pytest.raises(GenerationError): get_generation_provider("unknown", settings())


@pytest.mark.parametrize("failure,message", [
    (HTTPError("https://api.openai.com/v1/responses", 401, "private", {}, BytesIO(b"private key")), "authentication"),
    (HTTPError("https://api.openai.com/v1/responses", 429, "private", {}, BytesIO(b"private quota")), "quota"),
    (HTTPError("https://api.openai.com/v1/responses", 500, "private", {}, BytesIO(b"private")), "failed"),
    (HTTPError("https://api.openai.com/v1/responses", 302, "private redirect", {}, BytesIO()), "failed"),
    (URLError("private address"), "unavailable"), (TimeoutError("private"), "timed out"),
])
def test_transport_errors_are_sanitized_without_retries(monkeypatch, failure, message):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            assert request.full_url == "https://api.openai.com/v1/responses"
            assert request.get_header("Authorization") == "Bearer private-provider-key"
            assert timeout == 45
            raise failure
    monkeypatch.setattr("app.generation_providers.build_opener", lambda *args: Opener())
    with pytest.raises(ProviderUnavailable, match=message) as error:
        post_response({"model": OPENAI_MODEL}, "private-provider-key", 45)
    assert "private" not in str(error.value) and len(calls) == 1


@pytest.mark.parametrize("raw", [b"invalid", b"x" * (MAX_RESPONSE_BYTES + 1)])
def test_invalid_and_oversized_http_response(monkeypatch, raw):
    class Opener:
        def open(self, request, timeout): return BytesIO(raw)
    monkeypatch.setattr("app.generation_providers.build_opener", lambda *args: Opener())
    with pytest.raises(ProviderUnavailable): post_response({}, "private-provider-key", 45)
