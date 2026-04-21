from dataclasses import dataclass
from typing import NotRequired, TypedDict


class CSPosition(TypedDict):
    x: float
    y: float


class WorldUpdatePayload(TypedDict):
    type: str
    energy_price: NotRequired[float]
    electricity_price: NotRequired[float]
    solar_production_rate: NotRequired[float]
    grid_load: NotRequired[float]
    renewable_available: NotRequired[bool]
    tick_id: NotRequired[int]
    timestamp: NotRequired[str]


class WorldStatsEvent(TypedDict):
    event: str
    kwh: NotRequired[float]
    cost: NotRequired[float]
    minutes: NotRequired[float]
    current_load: NotRequired[float]
    renewable: NotRequired[bool]


class DailyMetricsSnapshot(TypedDict):
    energy_consumed: float
    charging_cost: float
    avg_waiting_time: float
    charging_sessions: int
    missed_spots: int
    renewable_pct: float
    peak_load: float


@dataclass(frozen=True)
class WorldAgentTiming:
    broadcast_period_seconds: float = 2.0
    daily_metrics_period_seconds: float = 1.0
    broadcast_heartbeat_seconds: float = 30.0