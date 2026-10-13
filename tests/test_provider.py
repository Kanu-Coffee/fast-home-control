import json

import httpx
import pytest
from fhc.config import Options
from fhc.provider import DecisionError, Provider, choice, noul


@pytest.mark.parametrize("azure", [False, True])
async def test_provider_contract_and_standalone_azure(azure):
    options = (
        Options(
            azure_api_key="test-only",
            azure_endpoint="https://test.example",
            azure_deployment="my-deployment",
        )
        if azure
        else Options(openrouter_api_key="test-only")
    )
    provider = Provider(options)
    requests = []

    def respond(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body["model"] == ("my-deployment" if azure else "microsoft/microsoft-decision-1")
        assert (
            (request.headers.get("api-key") == "test-only")
            if azure
            else (request.headers["authorization"] == "Bearer test-only")
        )
        return httpx.Response(
            200, json={"answers": {key: {"type": "noul", "noul": 0.9} for key in body["questions"]}}
        )

    await provider.http.aclose()
    provider.http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    answers, used = await provider.decide({"command": "불 꺼줘"}, {"ok": {"type": "noul"}})
    assert answers["ok"]["noul"] == 0.9
    assert used == ("azure" if azure else "openrouter")
    assert str(requests[0].url).endswith(
        "/providers/microsoft/v1/systemone" if azure else "/api/alpha/decisions"
    )
    await provider.close()


async def test_batching_keeps_every_question_and_full_catalog():
    provider = Provider(Options(openrouter_api_key="test-only"))
    seen = set()

    def respond(request):
        body = json.loads(request.content)
        assert body["state"]["full_catalog"] == ["all entities, no top-k"]
        seen.update(body["questions"])
        return httpx.Response(
            200,
            json={"answers": {key: {"type": "noul", "noul": 0.99} for key in body["questions"]}},
        )

    await provider.http.aclose()
    provider.http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    questions = {f"e{i}": {"type": "noul"} for i in range(200)}
    answers, _ = await provider.decide({"full_catalog": ["all entities, no top-k"]}, questions)
    assert set(answers) == seen == set(questions)
    await provider.close()


@pytest.mark.parametrize("value", [True, -1, 1.1, float("nan"), "0.99", None])
def test_invalid_probabilities_rejected(value):
    with pytest.raises(DecisionError):
        noul({"type": "noul", "noul": value})


def test_selected_label_must_have_high_probability_and_valid_distribution():
    with pytest.raises(DecisionError):
        choice(
            {"type": "choice", "choice": "on", "probabilities": {"on": 0.4, "off": 0.6}},
            {"on", "off"},
        )


async def test_invalid_model_answer_does_not_failover_to_seek_approval():
    provider = Provider(
        Options(
            openrouter_api_key="test-only",
            azure_api_key="test-only",
            azure_endpoint="https://test.example",
            azure_deployment="x",
        )
    )
    await provider.http.aclose()
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"answers": {}})

    provider.http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with pytest.raises(DecisionError, match="invalid_model_response"):
        await provider.decide({}, {"ok": {"type": "noul"}})
    assert len(seen) == 1
    await provider.close()
