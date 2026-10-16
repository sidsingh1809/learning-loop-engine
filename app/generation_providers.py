"""One Track B contract, with explicit selection and no silent AI fallback."""
from dataclasses import dataclass
import json
import socket
from pathlib import Path
from typing import Callable, Optional, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.config import Settings
from app.generation_schemas import GeneratedSequence
from app.generator import GENERATOR_VERSION, GenerationError, build_sequence, validate_output
from app.planner_schemas import DecisionRead, PlannerInput

OPENAI_MODEL = "gpt-6-luna"
OPENAI_GENERATOR_VERSION = "track-b-openai-v2"
PROMPT_VERSION = "programming-sequence-v2"
TEMPLATE_PROMPT_VERSION = "template-instructions-v1"
MAX_RESPONSE_BYTES = 256 * 1024


class ProviderUnavailable(GenerationError):
    """Configuration or upstream failure, safe to return without provider internals."""


@dataclass(frozen=True)
class ProviderSpec:
    provider: str
    model: Optional[str]
    prompt_version: str
    generator_version: str


TEMPLATE_SPEC = ProviderSpec("template", None, TEMPLATE_PROMPT_VERSION, GENERATOR_VERSION)
OPENAI_SPEC = ProviderSpec("openai", OPENAI_MODEL, PROMPT_VERSION, OPENAI_GENERATOR_VERSION)
# Retain historical prompt identities for frozen candidates; only v2 creates new AI content.
OPENAI_V1_SPEC = ProviderSpec("openai", OPENAI_MODEL, "programming-sequence-v1", "track-b-openai-v1")
PROVIDER_SPECS = {spec.generator_version: spec for spec in (TEMPLATE_SPEC, OPENAI_V1_SPEC, OPENAI_SPEC)}


class GenerationProvider(Protocol):
    spec: ProviderSpec

    def generate(self, snapshot: PlannerInput, decision: DecisionRead,
                 context_variant: str) -> GeneratedSequence:
        ...


class TemplateProvider:
    spec = TEMPLATE_SPEC

    def __init__(self, builder: Callable = build_sequence):
        self.builder = builder

    def generate(self, snapshot, decision, context_variant):
        return validate_output(self.builder(snapshot, decision, context_variant), snapshot, decision)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_response(body, api_key, timeout):
    """Fixed HTTPS destination; never follow a redirect with a credential."""
    request = Request("https://api.openai.com/v1/responses", method="POST",
        data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + api_key,
                                                "Content-Type": "application/json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderUnavailable("OpenAI response exceeded the size limit")
        return json.loads(raw)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        if status in (401, 403):
            message = "OpenAI authentication or model access failed; check the server API key and project access"
        elif status == 429:
            message = "OpenAI quota or rate limit reached"
        else:
            message = "OpenAI generation request failed"
        raise ProviderUnavailable(message) from None
    except (URLError, TimeoutError, socket.timeout, OSError):
        raise ProviderUnavailable("OpenAI generation unavailable or timed out") from None
    except (ValueError, UnicodeError):
        raise ProviderUnavailable("OpenAI returned an invalid response") from None


def strict_schema(value):
    """Adapt Pydantic's discriminated unions to OpenAI's strict JSON Schema subset."""
    if isinstance(value, list):
        return [strict_schema(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {("anyOf" if k == "oneOf" else k): strict_schema(v) for k, v in value.items()
              if k not in {"discriminator", "default", "title", "format"}}
    if "const" in result:
        result["enum"] = [result.pop("const")]
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    return result


def response_body(snapshot, decision, context_variant):
    # The validated reference bounds this first integration to the existing pilot.
    reference = build_sequence(snapshot, decision, context_variant).model_dump(mode="json")
    reference["generator_version"] = OPENAI_GENERATOR_VERSION
    return {"model": OPENAI_MODEL, "store": False, "reasoning": {"effort": "low"}, "max_output_tokens": 8000,
        "instructions": (Path(__file__).with_name("prompts") / (PROMPT_VERSION + ".txt")).read_text().strip(),
        "input": json.dumps({"reference_sequence": reference,
            "learner_skill_bands": [{"skill_id": s.skill_id, "band": s.band} for s in snapshot.states],
            "skills": [s.model_dump(mode="json") for s in snapshot.skills],
            "plan": decision.model_dump(mode="json"),
            "learning_science_rules": snapshot.learning_science_policy.rules.model_dump(mode="json"),
            "safety_rules": snapshot.safety_policy.rules.model_dump(mode="json")}, sort_keys=True),
        "text": {"format": {"type": "json_schema", "name": "learning_sequence",
                              "strict": True, "schema": strict_schema(GeneratedSequence.model_json_schema())}}}


class OpenAIProvider:
    spec = OPENAI_SPEC

    def __init__(self, settings: Settings, transport: Callable = post_response):
        self.settings, self.transport = settings, transport

    def generate(self, snapshot, decision, context_variant):
        if not self.settings.openai_generation_enabled:
            raise ProviderUnavailable("OpenAI generation is disabled; set OPENAI_GENERATION_ENABLED=true on the server")
        key = self.settings.openai_api_key
        if key is None or not key.get_secret_value().strip():
            raise ProviderUnavailable("OpenAI generation requires a server-side OPENAI_API_KEY")
        body = response_body(snapshot, decision, context_variant)
        raw = self.transport(body, key.get_secret_value(), self.settings.openai_timeout_seconds)
        try:
            if raw.get("status") != "completed" or raw.get("model") != OPENAI_MODEL:
                raise ProviderUnavailable("OpenAI returned an incomplete response or an unexpected model")
            parts = [part for item in raw["output"] if item.get("type") == "message"
                     for part in item["content"]]
            if any(part.get("type") == "refusal" for part in parts):
                raise ProviderUnavailable("OpenAI declined to generate this activity sequence")
            texts = [part["text"] for part in parts if part.get("type") == "output_text"]
            if len(texts) != 1:
                raise ProviderUnavailable("OpenAI returned no unique activity sequence")
            candidate = validate_output(json.loads(texts[0]), snapshot, decision)
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            if isinstance(exc, ProviderUnavailable):
                raise
            raise GenerationError("OpenAI generated invalid activity content") from None
        if candidate.generator_version != self.spec.generator_version or candidate.template_version != context_variant:
            raise GenerationError("OpenAI generated inconsistent provenance or context")
        return candidate


def get_generation_provider(name: str, settings: Settings, template_builder: Callable = build_sequence) -> GenerationProvider:
    if name == "template":
        return TemplateProvider(template_builder)
    if name == "openai":
        return OpenAIProvider(settings)
    raise GenerationError("Unsupported generation provider")
