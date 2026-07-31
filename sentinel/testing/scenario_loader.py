from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json


@dataclass
class Scenario:
    name: str
    input_text: str
    expected: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "input": {"text": self.input_text}, "expected": self.expected}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Scenario":
        return cls(
            name=d.get("name", "unnamed"),
            input_text=d.get("input", {}).get("text", ""),
            expected=d.get("expected", {}),
        )


class ScenarioLoader:
    def __init__(self, scenarios: Optional[List[Scenario]] = None):
        self._scenarios: List[Scenario] = scenarios or []

    def load_json(self, path: str) -> List[Scenario]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else [data]
        self._scenarios = [Scenario.from_dict(item) for item in items]
        return self._scenarios

    def load_dict(self, data: Dict[str, Any]) -> List[Scenario]:
        items = data if isinstance(data, list) else [data]
        self._scenarios = [Scenario.from_dict(item) for item in items]
        return self._scenarios

    def add(self, scenario: Scenario) -> None:
        self._scenarios.append(scenario)

    @property
    def scenarios(self) -> List[Scenario]:
        return list(self._scenarios)
