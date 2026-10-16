"""Check the shared contract locally, or generate a draft from a retained learner plan."""
import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from app.config import get_settings
from app.generation_providers import OPENAI_SPEC, OpenAIProvider, ProviderUnavailable, TemplateProvider
from app.generator import build_sequence, content_hash
from app.planner import build_plan
from app.planner_fixtures import synthetic_input


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-id", type=UUID)
    parser.add_argument("--expect-disabled", action="store_true")
    parser.add_argument("--context-variant", choices=["positive-sales-v1", "positive-donations-v1"], default="positive-sales-v1")
    args = parser.parse_args()
    snapshot = synthetic_input("beginner"); decision = build_plan(snapshot)
    sequence = TemplateProvider().generate(snapshot, decision, args.context_variant)
    assert sequence == build_sequence(snapshot, decision, args.context_variant)
    print("Template adapter: {} connected activities; unchanged hash {}".format(len(sequence.steps), content_hash(sequence)))
    print("Selected AI provider: {}; model: {}; prompt: {}".format(OPENAI_SPEC.provider, OPENAI_SPEC.model, OPENAI_SPEC.prompt_version))
    # Exercise the actual disabled adapter without touching settings or the network.
    disabled = get_settings().model_copy(update={"openai_generation_enabled": False})
    try:
        OpenAIProvider(disabled).generate(snapshot, decision, args.context_variant)
    except ProviderUnavailable as exc:
        print("Disabled-provider check: " + str(exc))
    else:
        raise AssertionError("Disabled provider must fail explicitly")
    if args.plan_id is None:
        print("Local contract check only; no OpenAI request. Add --plan-id to verify the running API.")
        return
    values = dotenv_values(ROOT / ".env")
    principals = json.loads(values.get("DEV_PRINCIPALS", "[]"))
    learner_key = next(p["api_key"] for p in principals if p["roles"] == ["learner"])
    instructor_key = next(p["api_key"] for p in principals if p["roles"] == ["instructor"])

    def request(method, path, payload=None, credential=learner_key, expected=(200,)):
        req = Request("http://127.0.0.1:8000" + path, method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"X-API-Key": credential, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=70) as response:
                status, result = response.status, json.load(response)
        except HTTPError as exc:
            status, result = exc.code, json.load(exc)
        except (URLError, TimeoutError):
            raise SystemExit("Local API unavailable or timed out; no verification claim.") from None
        print("{} {} → {}".format(method, path, status))
        if status not in expected:
            raise SystemExit("API check failed: " + str(result.get("detail", "unexpected response")))
        return status, result

    pp = "/api/v1/loop-plans/" + str(args.plan_id)
    _, original = request("GET", pp)
    _, learner = request("POST", "/api/v1/learners", {}, expected=(200, 201))
    ep = "/api/v1/learners/{}/enrollments/{}".format(learner["id"], original["enrollment_id"])
    _, before = request("GET", ep + "/state")
    _, history_before = request("GET", pp + "/generations")
    payload = {"provider": "openai", "context_variant": args.context_variant}
    status, generation = request("POST", pp + "/generations", payload, expected=(503,) if args.expect_disabled else (200, 201))
    if args.expect_disabled:
        assert "disabled" in generation["detail"]
        assert request("GET", pp + "/generations")[1] == history_before
        print("Disabled provider rejected by HTTP; no generation stored.")
        return
    assert (generation["provider"], generation["model"], generation["prompt_version"], generation["generator_version"]) == (
        OPENAI_SPEC.provider, OPENAI_SPEC.model, OPENAI_SPEC.prompt_version, OPENAI_SPEC.generator_version)
    gp = "/api/v1/activity-generations/" + generation["id"]
    _, reviewed = request("GET", gp + "/review-content", credential=instructor_key)
    assert reviewed["candidate"]["plan_fingerprint"] == original["decision"]["input_fingerprint"]
    assert request("POST", pp + "/generations", payload)[1] == generation
    assert request("GET", ep + "/state")[1] == before
    assert request("GET", pp)[1] == original
    if generation["review_status"] == "draft":
        for activity in generation["activities"]:
            request("GET", "/api/v1/activities/" + activity["id"], expected=(404,))
    print("Generation: {}; status: {}; content hash: {}".format(generation["id"], generation["review_status"], generation["content_hash"]))
    print("Fresh API generation verified." if status == 201 else "Existing frozen candidate reused; this run made no new provider call.")
    print("Plan and learner state unchanged; inspect /review-content as instructor before approval.")


if __name__ == "__main__":
    main()
