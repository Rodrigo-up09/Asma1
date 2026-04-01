from dataclasses import dataclass
from typing import Any, Mapping


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
            max_charging_rate=float(
                data.get("max_charging_rate", data.get("max_power_kw", cls.max_charging_rate))
            ),
            num_doors=int(data.get("num_doors", cls.num_doors)),
            max_solar_capacity=float(data.get("max_solar_capacity", cls.max_solar_capacity)),
            actual_solar_capacity=float(data.get("actual_solar_capacity", cls.actual_solar_capacity)),
            energy_price=float(data.get("energy_price", cls.energy_price)),
            solar_production_rate=float(data.get("solar_production_rate", cls.solar_production_rate)),
            x=float(data.get("x", cls.x)),
            y=float(data.get("y", cls.y)),
        )
