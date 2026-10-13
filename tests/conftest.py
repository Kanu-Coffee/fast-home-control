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
        self.timeout = False

    async def fresh_state(self, entity_id):
        return copy.deepcopy(self.states[entity_id])

    async def call(self, domain, service, entity_id):
        self.calls.append((domain, service, entity_id))
        if self.timeout:
            raise HAError("lost_ack")
        self.states[entity_id]["state"] = "on" if service == "turn_on" else "off"
        return {}


class ScriptedProvider:
    """Prescribed decisions test plumbing, never Korean model accuracy."""

    def __init__(self, targets=None, supported=True, exact=True):
        self.inputs = []
        self.targets = targets or {"천장등": "turn_off"}
        self.supported, self.exact = supported, exact

    async def decide(self, state, questions):
        self.inputs.append((copy.deepcopy(state), copy.deepcopy(questions)))
        names = {d["id"]: d["name"] for d in state.get("details", [])}
        answers = {}
        for key, question in questions.items():
            if question["type"] == "noul":
                value = (
                    self.exact if key == "exact" else self.supported if key == "supported" else True
                )
                answers[key] = {"type": "noul", "noul": 0.99 if value else 0.01}
            else:
                selected = self.targets.get(names[key], "none")
                answers[key] = {
                    "type": "choice",
                    "choice": selected,
                    "probabilities": {
                        name: 0.99 if name == selected else 0.005 for name in question["criteria"]
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
