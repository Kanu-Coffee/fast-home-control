import json
import math

import httpx

from .config import Options


class DecisionError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def choice(answer, options, minimum=0.9):
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise DecisionError("invalid_model_response")
    selected = answer.get("choice")
    probabilities = answer.get("probabilities")
    if (
        selected not in options
        or not isinstance(probabilities, dict)
        or set(probabilities) != set(options)
    ):
        raise DecisionError("invalid_model_response")
    values = [probability(p) for p in probabilities.values()]
    if abs(sum(values) - 1) > 0.02:
        raise DecisionError("invalid_model_response")
    selected_probability = probabilities[selected]
    others = [v for k, v in probabilities.items() if k != selected]
    if selected_probability < minimum or (others and selected_probability - max(others) < 0.2):
        raise DecisionError("low_confidence")
    return selected


def probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DecisionError("invalid_model_response")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise DecisionError("invalid_model_response")
    return value


def noul(answer):
    if not isinstance(answer, dict) or answer.get("type") != "noul":
        raise DecisionError("invalid_model_response")
    return probability(answer.get("noul"))


class Provider:
    def __init__(self, options: Options):
        self.options = options
        self.http = httpx.AsyncClient(timeout=20, trust_env=False)
        self.status = {name: "configured_unverified" for name in options.configured()}
        self.calls = 0

    async def decide(self, state, questions):
        # Inspect every question. Batching never discards entities through top-K retrieval.
        keys = list(questions)
        if len(keys) > 8:
            combined, used = {}, []
            for index in range(0, len(keys), 8):
                batch = {key: questions[key] for key in keys[index : index + 8]}
                context = dict(state)
                if "details" in context:
                    context["details"] = [d for d in context["details"] if d["id"] in batch]
                answers, name = await self.decide(context, batch)
                combined.update(answers)
                used.append(name)
            return combined, ",".join(dict.fromkeys(used))
        providers = self.options.configured()
        if not providers:
            raise DecisionError("provider_not_configured")
        last_error = "provider_unavailable"
        for name in providers:
            if name == "openrouter":
                url = "https://openrouter.ai/api/alpha/decisions"
                headers = {
                    "Authorization": "Bearer " + self.options.openrouter_api_key.get_secret_value()
                }
                model = "microsoft/microsoft-decision-1"
            else:
                url = self.options.azure_endpoint.rstrip("/") + "/providers/microsoft/v1/systemone"
                headers = {"api-key": self.options.azure_api_key.get_secret_value()}
                model = self.options.azure_deployment
            body = {"model": model, "state": state, "questions": questions}
            # Conservative local request budget, not an assumed provider token guarantee.
            if len(json.dumps(body, ensure_ascii=False).encode()) > 40000 or len(questions) > 64:
                raise DecisionError("catalog_too_large")
            try:
                self.calls += 1
                response = await self.http.post(url, headers=headers, json=body)
                if response.status_code != 200:
                    last_error = {
                        401: "provider_authentication_failed",
                        403: "provider_forbidden",
                        402: "provider_credit_required",
                        429: "provider_rate_limited",
                    }.get(response.status_code, f"provider_http_{response.status_code}")
                    self.status[name] = last_error
                    continue
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                last_error = "provider_communication_failed"
                self.status[name] = last_error
                continue
            answers = payload.get("answers") if isinstance(payload, dict) else None
            if not isinstance(answers, dict) or set(answers) != set(questions):
                self.status[name] = "invalid_model_response"
                # An invalid decision is never retried to seek a more permissive answer.
                raise DecisionError("invalid_model_response")
            self.status[name] = "connected"
            return answers, name
        raise DecisionError(last_error)

    async def close(self):
        await self.http.aclose()
