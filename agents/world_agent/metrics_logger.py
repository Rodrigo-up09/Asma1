from pathlib import Path


class ScenarioMetricsLogWriter:
    """Persist world metrics snapshots into scenario-specific log files."""

    def __init__(self, scenario_type: str, logs_dir: Path | None = None) -> None:
        root_dir = Path(__file__).resolve().parents[2]
        self.logs_dir = logs_dir or (root_dir / "logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.scenario_type = self._sanitize_name(scenario_type)
        self.log_file_path = self.logs_dir / f"{self.scenario_type}.txt"

    @staticmethod
    def _sanitize_name(raw_name: str) -> str:
        cleaned = "".join(ch for ch in str(raw_name) if ch.isalnum() or ch in ("-", "_"))
        return cleaned or "UnknownScenario"

    def write_daily_metrics(self, day_number: int, sim_time: str, metrics: dict) -> None:
        lines = [
            f"Day {day_number} (closed at sim-time {sim_time})",
            f"  Total Energy Consumed : {metrics['energy_consumed']:.2f} kWh",
            f"  Total Charging Cost   : {metrics['charging_cost']:.2f} EUR",
            f"  Avg Waiting Time      : {metrics['avg_waiting_time']:.2f} min",
            f"  Charging Sessions     : {metrics['charging_sessions']}",
            f"  Renewable Utilization : {metrics['renewable_pct']:.1f}%",
            f"  Peak Load             : {metrics['peak_load']:.2f} kW",
            f"  Peak Load Reduction   : {metrics['peak_load_reduction']:.1f}%",
            f"  SoC Success Rate      : {metrics['soc_success_rate']:.1f}%",
            "",
        ]
        with self.log_file_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))
