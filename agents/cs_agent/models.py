from dataclasses import dataclass
from typing import Any, Literal, Mapping, NotRequired, TypedDict


DecisionType = Literal["accept", "wait"]
WorldUpdateType = Literal["energy-price-update", "solar-production-rate-update"]


class ChargingRequest(TypedDict):
    ev_jid: str
    required_energy: float
    max_charging_rate: float
    arriving_hours: NotRequired[float]


class PendingProposal(TypedDict):
    request: ChargingRequest
    decision: DecisionType
    reserves_slot: bool
    created_at: float
    expires_at: float


class IncomingRequest(TypedDict):
    arriving_hours: float
    required_energy: float
    max_charging_rate: float


class ActiveChargingSession(TypedDict):
    required_energy: float
    rate: float
    price: float


class StationSnapshot(TypedDict):
    jid: str
    used_doors: int
    expected_evs: int
    num_doors: int
    electricity_price: float
    actual_solar_capacity: float
    max_solar_capacity: float
    solar_production_rate: float
    x: float
    y: float


class WorldUpdatePayload(TypedDict):
    type: WorldUpdateType
    energy_price: NotRequired[float]
    solar_production_rate: NotRequired[float]
    grid_load: NotRequired[float]
    renewable_available: NotRequired[bool]


@dataclass
class CSConfig:
    max_charging_rate: float = 22.0   # kW por porta
    num_doors: int = 4                # nº máximo de carros simultâneos

    max_solar_capacity: float = 150.0   # kW pico (teórico)
    actual_solar_capacity: float = 0.0  # kW atual (dinâmico)

    energy_price: float = 0.20       # €/kWh (grid)
    solar_production_rate: float = 15   

    x: float = 0.0
    y: float = 0.0
    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CSConfig":
        return cls(
            max_charging_rate=float(data.get("max_charging_rate", cls.max_charging_rate)),
            num_doors=int(data.get("num_doors", cls.num_doors)),
            max_solar_capacity=float(data.get("max_solar_capacity", cls.max_solar_capacity)),
            actual_solar_capacity=float(data.get("actual_solar_capacity", cls.actual_solar_capacity)),
            energy_price=float(data.get("energy_price", cls.energy_price)),
            solar_production_rate=float(data.get("solar_production_rate", cls.solar_production_rate)),
            x=float(data.get("x", cls.x)),
            y=float(data.get("y", cls.y)),
        )
