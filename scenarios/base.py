"""
Base Scenario class and helper functions.
"""


class Scenario:
    """Base scenario configuration."""
    
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.start_hour = 7.0
        self.num_evs = 1
        self.num_css = 1
        self.night_driver_ratio = 0.0
        self.cs_configs = []
        self.ev_configs = []
        self.spots = []  # Available spots for this scenario
    
    def __repr__(self):
        return f"{self.name}: {self.description}"
