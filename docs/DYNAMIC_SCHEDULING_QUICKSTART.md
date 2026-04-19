"""
Quick Start Guide: Dynamic Schedule Regeneration
=================================================

Method 1: Use the Built-in DynamicScheduling Scenario (Easiest)
================================================================

1. Run main.py:
   $ python main.py

2. Select scenario 4: "Dynamic Scheduling"

3. Watch the simulation - each day EVs get new random destinations!

The scenario automatically handles everything:
- 5 EVs with randomized routes
- 2 charging stations
- 20% night drivers
- Fixed appointment times, changing destinations daily


Method 2: Enable in Your Custom Scenario
=========================================

To add dynamic scheduling to an existing scenario:

Step 1: Define available spots in your scenario
-----------------------------------------------

class MyScenario(Scenario):
    def __init__(self):
        super().__init__("My Scenario", "Description")
        
        # IMPORTANT: Define spots for dynamic regeneration
        self.spots = [
            {"name": "Location 1", "x": 10.0, "y": 10.0},
            {"name": "Location 2", "x": -10.0, "y": -10.0},
            {"name": "Location 3", "x": 15.0, "y": -5.0},
            # ... as many as you want ...
        ]
        
        # Continue with EV and CS configs as normal
        self.ev_configs = [...]
        self.cs_configs = [...]


Step 2: Add available_spots to EV config
-----------------------------------------

In your scenario's EV config dict:

self.ev_configs.append({
    "jid": f"ev{i}@localhost",
    "password": "password",
    "config": {
        "battery_capacity_kwh": 60.0,
        "current_soc": 0.50,
        "x": 5.0,
        "y": 5.0,
        "schedule": initial_schedule,  # Day 0 base
        "available_spots": self.spots,  # ← ENABLE DYNAMIC SCHEDULING
        "num_schedule_stops": 4,         # ← Stops per day
        # ... other fields ...
    }
})


Step 3: main.py automatically integrates
----------------------------------------

main.py already passes scenario.spots to EVs:

"available_spots": scenario.spots,  # This line is in _generate_scenario_ev_deployment()

So it just works when you run your scenario!


Method 3: Manual Control (Advanced)
===================================

If you need programmatic access to regenerated schedules:

```python
# In your code that has access to an EV agent:

# Get schedule for day 0 (initial)
day_0_schedule = ev_agent.get_current_day_schedule()
print(f"Day 0: {[s['name'] for s in day_0_schedule]}")

# As simulation progresses and ev_agent._day_offset changes to 1:
day_1_schedule = ev_agent.get_current_day_schedule()
print(f"Day 1: {[s['name'] for s in day_1_schedule]}")

# Schedule has been regenerated! Different destinations.
```


How to Check If It's Working
=============================

1. Visual Check:
   - Run simulation with visualization
   - Watch the target diamonds on the map
   - They should move/change position each day

2. Log Check:
   - Add debugging to schedule_manager.py:
   
   def _generate_day_schedule(self, day):
       schedule = [...]
       print(f"[Day {day}] Generated schedule: {[s['name'] for s in schedule]}")
       return schedule
   
   - Run simulation and check console output
   - Should see different destinations each day

3. Code Check:
   - EVAgent has self.schedule_manager set (not None)
   - self.schedule_manager.available_spots is populated
   - EVAgent.next_target() calls schedule_manager.get_schedule_for_day()


Customization Options
====================

In ScheduleManager constructor:

ScheduleManager(
    home_x=5.0,
    home_y=5.0,
    available_spots=spots_list,
    num_stops=4,  # ← Change this to vary stops/day
)

- num_stops=2  : Only 2 appointments + home (3 destinations)
- num_stops=4  : 4 appointments + home (5 destinations) [DEFAULT]
- num_stops=6  : 6 appointments + home (7 destinations)

More stops = busier EVs = higher charging demand


Troubleshooting
===============

Q: Schedule not changing between days?
A: Check that:
   - available_spots is not empty in scenario.spots
   - EV config contains "available_spots" field
   - _day_offset is actually incrementing (check driving.py)

Q: NameError: ScheduleManager not found?
A: Add import to ev_agent.py:
   from .schedule_manager import ScheduleManager

Q: Same destinations every day?
A: Random seed issue - check if random.seed() is set globally
   The system uses random.choice() which should vary

Q: Want to see old static schedules?
A: Don't pass available_spots to EV config - it falls back to static mode


File Reference
==============

Core files:
- agents/ev_agent/schedule_manager.py     (ScheduleManager class)
- agents/ev_agent/ev_agent.py              (Integration - next_target, get_current_day_schedule)
- scenarios/dynamic_scheduling.py          (Example scenario)
- main.py                                  (Deployment integration - ~line 152)
- docs/dynamic_scheduling.md               (Full documentation)

Supporting files (auto-updated):
- scenarios/__init__.py                    (Scenario registration)
- scenarios/base.py                        (Scenario base class)
"""
