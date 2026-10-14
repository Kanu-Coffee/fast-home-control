import copy

import pytest
from fhc.ha import HAError
from fhc.store import Store


class FakeHA:
    def __init__(self):
        self.ready, self.version = True, 1
        self.registry = [
            {"entity_id": "light.living", "area_id": "living", "aliases": ["큰등"]},
            {"entity_id": "light.bedroom", "area_id": "bedroom"},
            {"entity_id": "switch.living", "area_id": "living"},
        ]
        self.areas = [
            {"area_id": "living", "name": "거실", "aliases": ["응접실"]},
            {"area_id": "bedroom", "name": "침실"},
        ]
        self.devices = []
        self.states = {
            "light.living": {
                "entity_id": "light.living",
                "state": "on",
                "attributes": {"friendly_name": "천장등"},
            },
            "light.bedroom": {
                "entity_id": "light.bedroom",
                "state": "on",
                "attributes": {"friendly_name": "침실등"},
            },
            "switch.living": {
                "entity_id": "switch.living",
                "state": "off",
                "attributes": {"friendly_name": "콘센트"},
            },
        }
        self.services = {d: {"turn_on": {}, "turn_off": {}} for d in ["light", "switch"]}
        self.calls = []
        self.response_calls = []
        self.responses = {}
        self.timeout = False
        self.time_zone = "Asia/Seoul"

    async def fresh_state(self, entity_id):
        return copy.deepcopy(self.states[entity_id])

    async def call(self, domain, service, entity_id, service_data=None, return_response=False):
        if return_response:
            self.response_calls.append((domain, service, entity_id, service_data))
            # Real HA/Supervisor nests the payload under the entity id.
            return {
                "response": {entity_id: copy.deepcopy(self.responses.get((domain, service), {}))}
            }
        if service_data is not None:
            self.calls.append((domain, service, entity_id, service_data))
        else:
            self.calls.append((domain, service, entity_id))
        if self.timeout:
            raise HAError("lost_ack")
        state = self.states[entity_id]
        if domain == "climate":
            if service == "set_hvac_mode":
                state["state"] = service_data["hvac_mode"]
            elif service == "turn_off":
                state["state"] = "off"
            elif service == "turn_on":
                state["state"] = "cool"
            elif service == "set_temperature":
                state["attributes"].update(service_data)
                if "hvac_mode" in service_data:
                    state["state"] = service_data["hvac_mode"]
        elif service == "set_value":
            state["state"] = str(service_data["value"])
            state["attributes"].update(service_data)
        else:
            state["state"] = "on" if service == "turn_on" else "off"
            if service_data:
                for k, v in service_data.items():
                    if k == "brightness_pct":
                        state["attributes"]["brightness"] = round(v / 100 * 255)
                    elif k != "brightness_step_pct":
                        state["attributes"][k] = v
        return {}


class ScriptedProvider:
    """Prescribed decisions test plumbing, never Korean model accuracy."""

    def __init__(self, targets=None, supported=True, exact=True, conditional=None):
        self.inputs = []
        self.targets = targets or {"천장등": "turn_off"}
        self.supported, self.exact = supported, exact
        self.conditional = conditional

    def _condition_value(self, key, question):
        cond = self.targets.get("__condition__")
        if cond is None or isinstance(cond, str):
            cond = self.conditional if isinstance(self.conditional, dict) else None
        cond = cond or {}
        prop = key.split("condition_", 1)[1]
        selected = cond.get(prop, "none")
        if prop == "source":
            criteria = question["criteria"]
            if selected in criteria:
                pass
            else:
                hit = [
                    k for k, v in criteria.items() if isinstance(selected, str) and selected in v
                ]
                selected = hit[0] if len(hit) == 1 else "none"
        return selected

    async def decide(self, state, questions):
        self.inputs.append((copy.deepcopy(state), copy.deepcopy(questions)))
        names = {d["id"]: d["name"] for d in state.get("details", [])}
        answers = {}
        for key, question in questions.items():
            if key == "condition_class":
                cond = self.targets.get("__condition__")
                selected = "none"
                if cond == "unclear":
                    selected = "unclear"
                elif isinstance(cond, dict):
                    selected = "typed"
                criteria = question["criteria"]
                answers[key] = {
                    "type": "choice",
                    "choice": selected,
                    "probabilities": {
                        name: 0.99 if name == selected else 0.01 / max(1, len(criteria) - 1)
                        for name in criteria
                    },
                }
            elif question["type"] == "noul":
                value = (
                    self.exact if key == "exact" else self.supported if key == "supported" else True
                )
                answers[key] = {"type": "noul", "noul": 0.99 if value else 0.01}
            elif key.startswith("condition_"):
                selected = self._condition_value(key, question)
                criteria = question["criteria"]
                if selected not in criteria:
                    selected = "none"
                answers[key] = {
                    "type": "choice",
                    "choice": selected,
                    "probabilities": {
                        name: 0.99 if name == selected else 0.01 / max(1, len(criteria) - 1)
                        for name in criteria
                    },
                }
            else:
                ref, prop = key.split("_", 1)
                target = self.targets.get(names[ref], "none")
                if isinstance(target, dict):
                    selected = target.get(prop, "none")
                    if prop == "tts_output" and selected not in question["criteria"]:
                        hits = [
                            k
                            for k, v in question["criteria"].items()
                            if isinstance(selected, str) and selected in v
                        ]
                        selected = hits[0] if len(hits) == 1 else "none"
                else:
                    selected = "none"
                    if prop == "power" and target in {"turn_on", "turn_off"}:
                        selected = target
                    elif prop == "hvac" and target.startswith("mode_"):
                        selected = target.removeprefix("mode_")
                    elif prop == "temperature" and target == "set_temp":
                        selected = "v0"
                    elif prop == "color" and target == "set_color":
                        selected = "red"
                    elif prop == "brightness" and target in {"dim_down", "dim_up"}:
                        selected = target
                answers[key] = {
                    "type": "choice",
                    "choice": selected,
                    "probabilities": {
                        name: 0.99
                        if name == selected
                        else 0.01 / max(1, len(question["criteria"]) - 1)
                        for name in question["criteria"]
                    },
                }
        return answers, "scripted"


@pytest.fixture
def ha():
    return FakeHA()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path)
    yield s
    s.close()
