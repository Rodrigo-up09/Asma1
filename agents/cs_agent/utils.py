
def charging_time_minutes(required_energy_kwh, ev_rate_kw, cs_rate_kw):
        effective_rate = min(float(ev_rate_kw), float(cs_rate_kw))
        if effective_rate <= 0:
            return float("inf")
        required_energy = max(0.0, float(required_energy_kwh))
        return (required_energy / effective_rate) * 60.0