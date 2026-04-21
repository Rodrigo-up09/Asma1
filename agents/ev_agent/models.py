from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, NotRequired, TypedDict


WorldUpdateType = Literal["energy-price-update", "solar-production-rate-update"]


class StationInfo(TypedDict):
    jid: str
    x: float
    y: float
    electricity_price: float
    used_doors: int
    expected_evs: int
    num_doors: int
    actual_solar_capacity: float
    max_solar_capacity: float
    solar_production_rate: float
    estimated_wait_minutes: float


class EVResponse(TypedDict):
    status: str
    price: NotRequired[float]
    estimated_wait_minutes: NotRequired[float]
    reason: NotRequired[str]


class ScheduleStop(TypedDict):
    name: str
    x: float
    y: float
    hour: float
    type: NotRequired[str]


class WorldUpdatePayload(TypedDict):
    type: WorldUpdateType
    energy_price: NotRequired[float]
    electricity_price: NotRequired[float]
    solar_production_rate: NotRequired[float]
    grid_load: NotRequired[float]
    renewable_available: NotRequired[bool]


@dataclass
class EVConfig:
    battery_capacity_kwh: float = 60.0
    current_soc: float = 0.20
    low_soc_threshold: float = 0.20
    target_soc: float = 0.80

    departure_time: str = "08:00"
    arrival_time: str = "22:00"

    max_charge_rate_kw: float = 22.0
    velocity: float = 1.0
    energy_per_km: float = 1.0

    x: float = 0.0
    y: float = 0.0

    cs_selection_mode: str = "score"
    electricity_price: float = 0.15
    grid_load: float = 0.5
    renewable_available: bool = False
    world_jid: str = ""

    cs_stations: list[StationInfo] = field(default_factory=list)
    schedule: list[ScheduleStop] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EVConfig":
        stations = data.get("cs_stations", [])
        schedule = data.get("schedule", [])

        parsed_stations: list[StationInfo] = []
        for station in stations:
            parsed_stations.append(
                {
                    "jid": str(station.get("jid", "")),
                    "x": float(station.get("x", 0.0)),
                    "y": float(station.get("y", 0.0)),
                    "electricity_price": float(station.get("electricity_price", 0.15)),
                    "used_doors": int(station.get("used_doors", 0)),
                    "expected_evs": int(station.get("expected_evs", 0)),
                    "num_doors": int(station.get("num_doors", 2)),
                    "actual_solar_capacity": float(station.get("actual_solar_capacity", 0.0)),
                    "max_solar_capacity": float(station.get("max_solar_capacity", 1.0)),
                    "solar_production_rate": float(station.get("solar_production_rate", 0.0)),
                    "estimated_wait_minutes": float(station.get("estimated_wait_minutes", 0.0)),
                }
            )

        parsed_schedule: list[ScheduleStop] = []
        for stop in schedule:
            parsed_stop: ScheduleStop = {
                "name": str(stop.get("name", "Unknown")),
                "x": float(stop.get("x", 0.0)),
                "y": float(stop.get("y", 0.0)),
                "hour": float(stop.get("hour", 0.0)),
            }
            if "type" in stop:
                parsed_stop["type"] = str(stop.get("type", "destination"))
            parsed_schedule.append(parsed_stop)

        return cls(
            battery_capacity_kwh=float(data.get("battery_capacity_kwh", cls.battery_capacity_kwh)),
            current_soc=float(data.get("current_soc", cls.current_soc)),
            low_soc_threshold=float(data.get("low_soc_threshold", cls.low_soc_threshold)),
            target_soc=float(data.get("target_soc", cls.target_soc)),
            departure_time=str(data.get("departure_time", cls.departure_time)),
            arrival_time=str(data.get("arrival_time", cls.arrival_time)),
            max_charge_rate_kw=float(data.get("max_charge_rate_kw", cls.max_charge_rate_kw)),
            velocity=float(data.get("velocity", cls.velocity)),
            energy_per_km=float(data.get("energy_per_km", cls.energy_per_km)),
            x=float(data.get("x", cls.x)),
            y=float(data.get("y", cls.y)),
            cs_selection_mode=str(data.get("cs_selection_mode", cls.cs_selection_mode)),
            electricity_price=float(data.get("electricity_price", cls.electricity_price)),
            grid_load=float(data.get("grid_load", cls.grid_load)),
            renewable_available=bool(data.get("renewable_available", cls.renewable_available)),
            world_jid=str(data.get("world_jid", cls.world_jid)),
            cs_stations=parsed_stations,
            schedule=parsed_schedule,
        )