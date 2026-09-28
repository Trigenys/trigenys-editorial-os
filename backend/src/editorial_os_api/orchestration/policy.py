from dataclasses import dataclass, field

from editorial_os_api.domain.enums import GateKind, RiskClass

ALL_GATES = frozenset({GateKind.TOPIC, GateKind.EDITORIAL, GateKind.PUBLISH})


@dataclass(frozen=True)
class GatePolicy:
    """Configurable gate policy with MVP fail-closed defaults."""

    mvp_lock: bool = True
    required_by_default: frozenset[GateKind] = ALL_GATES
    vertical_required: dict[str, frozenset[GateKind]] = field(default_factory=dict)
    risk_required: dict[RiskClass, frozenset[GateKind]] = field(default_factory=dict)

    def required_gates(self, *, vertical_key: str, risk_class: RiskClass) -> frozenset[GateKind]:
        required = set(self.required_by_default)
        required.update(self.vertical_required.get(vertical_key, frozenset()))
        required.update(self.risk_required.get(risk_class, frozenset()))
        required.add(GateKind.PUBLISH)

        if self.mvp_lock:
            required.update(ALL_GATES)

        return frozenset(required)

    def is_required(
        self,
        gate: GateKind,
        *,
        vertical_key: str,
        risk_class: RiskClass,
    ) -> bool:
        return gate in self.required_gates(
            vertical_key=vertical_key,
            risk_class=risk_class,
        )
