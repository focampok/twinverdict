"""Contrato de la política: JSON validado, nunca código ejecutable."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MACHINES: tuple[str, ...] = ("M1", "M2", "M3", "M4", "M5")
PRODUCTS: tuple[str, ...] = ("P1", "P2", "P3")

MachineId = Literal["M1", "M2", "M3", "M4", "M5"]
ProductId = Literal["P1", "P2", "P3"]
DispatchRule = Literal["EDD", "SPT", "WEIGHTED", "CRITICAL_RATIO"]

DEFAULT_PM_THRESHOLD = 0.75

_RULES_NEEDING_WEIGHTS = frozenset({"WEIGHTED"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Maintenance(_Strict):
    pm_wear_threshold: dict[MachineId, float] = Field(default_factory=dict)
    max_pm_per_shift: int = Field(ge=0, le=3)

    @field_validator("pm_wear_threshold")
    @classmethod
    def _thresholds_in_range(cls, value: dict[MachineId, float]) -> dict[MachineId, float]:
        for machine, threshold in value.items():
            if not 0.30 <= threshold <= 0.95:
                raise ValueError(
                    f"pm_wear_threshold de {machine} debe estar entre 0.30 y 0.95, no {threshold}"
                )
        return value

    def threshold_for(self, machine: str) -> float:
        return self.pm_wear_threshold.get(machine, DEFAULT_PM_THRESHOLD)


class Weights(_Strict):
    due_date: float = Field(ge=0, le=1)
    wear_risk: float = Field(ge=0, le=1)
    setup: float = Field(ge=0, le=1)

    @property
    def total(self) -> float:
        return self.due_date + self.wear_risk + self.setup


class Dispatch(_Strict):
    rule: DispatchRule
    weights: Weights | None = None

    @model_validator(mode="after")
    def _require_and_normalize_weights(self) -> "Dispatch":
        if self.weights is None:
            if self.rule in _RULES_NEEDING_WEIGHTS:
                raise ValueError(f"weights es obligatorio cuando rule es {self.rule}")
            self.weights = Weights(due_date=1 / 3, wear_risk=1 / 3, setup=1 / 3)
            return self
        total = self.weights.total
        if total == 0:
            raise ValueError("la suma de weights es 0")
        if abs(total - 1.0) > 1e-9:
            self.weights = Weights(
                due_date=self.weights.due_date / total,
                wear_risk=self.weights.wear_risk / total,
                setup=self.weights.setup / total,
            )
        return self


class Condition(_Strict):
    machine: MachineId | None = None
    wear_gt: float | None = Field(default=None, ge=0.50, le=0.99)
    urgent_order_waiting: bool | None = None
    queue_len_gt: int | None = Field(default=None, ge=1, le=50)
    product_waiting: ProductId | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "Condition":
        present = (
            self.machine,
            self.wear_gt,
            self.urgent_order_waiting,
            self.queue_len_gt,
            self.product_waiting,
        )
        if all(item is None for item in present):
            raise ValueError("la condición debe incluir al menos un campo")
        return self


class PostponePM(_Strict):
    action: Literal["POSTPONE_PM"]
    max_minutes: int = Field(ge=15, le=240)


class ForcePM(_Strict):
    action: Literal["FORCE_PM"]
    machine: MachineId | None = None


class BatchSameProduct(_Strict):
    action: Literal["BATCH_SAME_PRODUCT"]


class PrioritizeProduct(_Strict):
    action: Literal["PRIORITIZE_PRODUCT"]
    product: ProductId


Action = Annotated[
    PostponePM | ForcePM | BatchSameProduct | PrioritizeProduct,
    Field(discriminator="action"),
]


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    cond: Condition = Field(alias="if")
    then_: Action = Field(alias="then")


class Policy(_Strict):
    maintenance: Maintenance
    dispatch: Dispatch
    rules: list[Rule] = Field(default_factory=list, max_length=5)
    version: int = 1


def parse_policy(raw: dict | str) -> Policy:
    if isinstance(raw, str):
        raw = json.loads(raw)
    return Policy.model_validate(raw)


def _dispatch_variant(rule: str, *, weights_required: bool) -> dict:
    if weights_required:
        weights: dict = {"$ref": "#/$defs/Weights"}
        required = ["rule", "weights"]
    else:
        weights = {"anyOf": [{"$ref": "#/$defs/Weights"}, {"type": "null"}]}
        required = ["rule"]
    return {
        "additionalProperties": False,
        "properties": {
            "rule": {"enum": [rule], "type": "string"},
            "weights": weights,
        },
        "required": required,
        "title": f"Dispatch_{rule}",
        "type": "object",
    }


def policy_json_schema() -> dict:
    """Esquema JSON de Policy para la decodificación guiada de vLLM.

    vLLM 0.27 responde 500 si el esquema incluye `propertyNames`. El dict de
    umbrales se declara con una clave por máquina. `weights` es obligatorio
    solo con rule WEIGHTED, vía oneOf: xgrammar no aplica bien if/then, y
    oneOf ya convivió con esta imagen cuando el único 500 era propertyNames.
    """
    schema = Policy.model_json_schema()
    threshold = schema["$defs"]["Maintenance"]["properties"]["pm_wear_threshold"]
    threshold.pop("propertyNames", None)
    threshold["properties"] = {
        machine: {"type": "number", "minimum": 0.30, "maximum": 0.95} for machine in MACHINES
    }
    threshold["additionalProperties"] = False
    mapping: dict[str, str] = {}
    one_of: list[dict[str, str]] = []
    for rule in ("EDD", "SPT", "WEIGHTED", "CRITICAL_RATIO"):
        name = f"Dispatch_{rule}"
        schema["$defs"][name] = _dispatch_variant(
            rule, weights_required=rule in _RULES_NEEDING_WEIGHTS
        )
        ref = f"#/$defs/{name}"
        mapping[rule] = ref
        one_of.append({"$ref": ref})
    schema["$defs"]["Dispatch"] = {
        "discriminator": {"mapping": mapping, "propertyName": "rule"},
        "oneOf": one_of,
        "title": "Dispatch",
    }
    return schema


def fixed_rule_policy() -> Policy:
    """Regla fija: EDD, umbral 0.75 en todas las máquinas, un PM por turno, sin reglas."""
    return Policy(
        maintenance=Maintenance(
            pm_wear_threshold={machine: DEFAULT_PM_THRESHOLD for machine in MACHINES},
            max_pm_per_shift=1,
        ),
        dispatch=Dispatch(rule="EDD"),
        rules=[],
    )
