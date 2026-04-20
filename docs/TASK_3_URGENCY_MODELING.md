# Task 3: Urgency Modeling for EV Scheduling

**Status**: ✅ **COMPLETE**

## Overview

Task 3 implements an urgency modeling system that influences EV charging priority and routing decisions based on appointment urgency and deadline proximity. EVs now make intelligent decisions about when to charge and how fast to drive based on time pressure.

---

## Architecture

### Core Component: UrgencyModel

**File**: `agents/ev_agent/urgency_model.py` (500+ lines)

#### Key Classes & Enums

**UrgencyLevel** - Maps to Priority multipliers:
```python
LOW = 1.0          # Flexible, opportunistic
MEDIUM = 2.0       # Regular, balanced
HIGH = 5.0         # Important, proactive
EMERGENCY = 10.0   # Critical, aggressive
```

**ChargingStrategy** - Determines charging behavior:
```python
OPPORTUNISTIC  # Charge only when necessary
BALANCED       # Charge at optimal times
AGGRESSIVE     # Charge whenever possible
```

**UrgencyMetrics** - Calculated decision factors:
```python
@dataclass
class UrgencyMetrics:
    urgency_level: UrgencyLevel        # Destination urgency
    time_pressure: float               # 0.0 (relaxed) to 1.0+ (critical)
    charging_multiplier: float         # 1.0-2.5x adjustment factor
    speed_adjustment: float            # 0.5x-2.0x speed multiplier
    charging_strategy: ChargingStrategy
    priority_score: float              # 0-100 ranking score
```

### Static Methods

#### `calculate_time_pressure()`
Measures urgency as a fraction (0.0 to 1.0+):
- Considers current time, target arrival, hard deadline
- Accounts for travel time and margin
- Values > 1.0 indicate already past deadline

#### `calculate_charging_threshold_adjustment()`
Determines SoC threshold multiplier based on urgency:
- **LOW**: 0.8x (relax, charge less often)
- **MEDIUM**: 1.0x (normal behavior)
- **HIGH**: 1.5x (charge more aggressively)
- **EMERGENCY**: 2.5x (charge whenever possible)

#### `calculate_metrics()`
Full calculation pipeline:
```python
metrics = UrgencyModel.calculate_metrics(
    current_time=10.0,
    destination=destination_with_time_window,
    current_soc=0.60,
    distance_to_destination=25.0,
    velocity=2.0
)
```

Returns `UrgencyMetrics` with all decision factors.

#### `get_charging_threshold()`
Applies urgency adjustment to base threshold:
```python
adjusted = UrgencyModel.get_charging_threshold(
    base_threshold=0.30,
    urgency_metrics=metrics
)
# Returns 0.30 * multiplier, clamped to max (e.g., 1.0)
```

#### `should_charge_now()`
Determines charging decision:
```python
should_charge = UrgencyModel.should_charge_now(
    current_soc=0.35,
    adjusted_threshold=0.45,
    urgency_metrics=metrics
)
```

Strategy-dependent:
- **OPPORTUNISTIC**: Only charge when very low (threshold * 0.8)
- **BALANCED**: Normal threshold
- **AGGRESSIVE**: Charge earlier (threshold * 1.2)

#### `rank_destinations()`
Prioritizes destinations by urgency:
```python
ranked = UrgencyModel.rank_destinations(
    destinations=[list of destination dicts],
    current_time=10.0,
    current_soc=0.60,
    current_x=0.0,
    current_y=0.0,
    velocity=2.0
)
# Returns sorted list: [(destination, metrics, score), ...]
```

---

## Integration Points

### StoppedState Enhancement

The `StoppedState` now uses urgency metrics when deciding whether to charge:

**Modified Methods**:
1. `_handle_charging_detour()` - Accepts `current_time` parameter
2. `_calculate_detour_path()` - Accepts `current_time` parameter
3. `_calculate_target_soc()` - Uses urgency to adjust charging targets

**Flow**:
```
StoppedState.run()
  → _get_next_stop_and_distances()
  → _calculate_timing(dist)  [gets current_time as 'now']
  → _handle_charging_detour(..., current_time=now)
    → _calculate_detour_path(..., current_time=now)
      → _calculate_target_soc(..., destination, current_time)
        [UrgencyModel.calculate_metrics() called here]
        [Charging threshold adjusted based on urgency]
```

### Charging Decision Logic

When determining if a charging detour is needed:
1. Calculate urgency metrics for destination
2. Get urgency-adjusted charging threshold
3. Apply charging strategy (opportunistic/balanced/aggressive)
4. Adjust `_trip_target_soc` based on urgency
5. Calculate charge time needed with adjusted target

**Example Log Output**:
```
[10.2][ev1][STOPPED] [Urgency: HIGH | Pressure: 0.65 | 
Strategy: aggressive | Priority Score: 35]
[10.2][ev1][STOPPED] Charging detour calculation:
  Trip target SoC: 65%  [boosted from 50% by urgency]
  ...
```

---

## Behavioral Changes

### Before (Task 2)
- EVs charged only when battery was low (fixed threshold)
- No consideration for appointment urgency
- Charging targets fixed regardless of deadline

### After (Task 3)
- **LOW Priority**: Charge less frequently, seek cheaper stations
- **MEDIUM Priority**: Balanced approach, charge at normal thresholds
- **HIGH Priority**: Charge more aggressively, ensure full battery
- **EMERGENCY Priority**: Maximum charging whenever possible

### Example Scenarios

**Scenario 1: Optional appointment (LOW)**
- Time: 9:00 | SoC: 35% | Threshold: 0.30
- Urgency: LOW, Strategy: OPPORTUNISTIC
- Decision: Don't charge (35% > 30% * 0.8)
- Speed: Normal (1.0x)

**Scenario 2: Important meeting (HIGH)**
- Time: 10:5 | SoC: 35% | Threshold: 0.30
- Urgency: HIGH, Strategy: BALANCED
- Adjusted Threshold: 0.30 * 1.5 = 45%
- Decision: Charge (35% < 45%)
- Speed: Speed up (1.5x)

**Scenario 3: Critical delivery (EMERGENCY)**
- Time: 10.8 | SoC: 40% | Threshold: 0.30
- Urgency: EMERGENCY, Strategy: AGGRESSIVE
- Adjusted Threshold: 0.30 * 2.5 = 75%
- Decision: Charge (40% < 75%)
- Speed: Maximum (2.0x)

---

## Scenario: UrgencyModelingScenario

**File**: `scenarios/urgency_modeling.py` (200+ lines)

Demonstrates urgency-based behavior with:
- **5 EVs** with varied battery capacities
- **4 Charging Stations** with different capabilities
- **Varied Appointments**:
  - 8:00 - MEDIUM: Morning routine (±1h window)
  - 10:30 - LOW: Optional meeting (±2h window)
  - 13:00 - HIGH: Important presentation (±45m window)
  - 15:30 - EMERGENCY: Critical delivery (±30m window)
  - 18:00 - MEDIUM: Evening errand (±1h window)
  - 20:00 - LOW: Return home (flexible, ±2h window)

**Helper Function**: `generate_urgency_schedule()`
- Creates schedules with mixed urgency levels
- Automatically sizes time windows based on urgency
- Generates hard deadlines with urgency-appropriate margins

---

## Validation Demo

**File**: `demo_urgency_model.py` (300+ lines)

Demonstrates:
1. **Urgency Levels** - Priority to urgency mapping
2. **Time Pressure** - Deadline urgency calculation
3. **Charging Thresholds** - Urgency-based adjustment
4. **Metrics Calculation** - Full pipeline
5. **Destination Ranking** - Priority-based sorting
6. **Charging Decision** - Should charge now logic

**Run**:
```bash
python3 demo_urgency_model.py
```

---

## Integration with Task 2

Urgency modeling **complements** time constraints:

- **Time Constraints** (Task 2): Define arrival windows and penalties
- **Urgency Model** (Task 3): Influence routing and charging decisions

Together they create:
- Realistic scheduling with mixed priorities
- Intelligent charging based on deadline pressure
- Speed adjustments for urgent appointments
- Priority-based routing decisions

---

## Files Changed

### New Files (3)
| File | Lines | Purpose |
|------|-------|---------|
| `agents/ev_agent/urgency_model.py` | 500+ | Core urgency framework |
| `scenarios/urgency_modeling.py` | 200+ | Demo scenario |
| `demo_urgency_model.py` | 300+ | Validation suite |

### Modified Files (3)
| File | Changes |
|------|---------|
| `agents/ev_agent/ev_agent.py` | Added UrgencyModel import |
| `agents/ev_agent/states/stopped.py` | Added urgency consideration in charging decisions |
| `scenarios/__init__.py` | Registered UrgencyModelingScenario |

---

## Usage

### Run Validation Demo
```bash
cd /home/lucasalf/Desktop/QuartoAno/segundoSemestre/ASMA/proj/Asma1
python3 demo_urgency_model.py
```

### Run Scenario
```bash
python3 main.py
# Select "6. Urgency Modeling" from menu
```

### Use in Code
```python
from agents.ev_agent.urgency_model import UrgencyModel

# Calculate metrics for a destination
metrics = UrgencyModel.calculate_metrics(
    current_time=10.0,
    destination=destination,
    current_soc=0.60,
    distance_to_destination=25.0,
    velocity=2.0
)

# Check if should charge
should_charge = UrgencyModel.should_charge_now(
    current_soc=0.35,
    adjusted_threshold=0.45,
    urgency_metrics=metrics
)

# Rank destinations by priority
ranked = UrgencyModel.rank_destinations(
    destinations=my_destinations,
    current_time=10.0,
    current_soc=0.60,
    current_x=0.0,
    current_y=0.0,
    velocity=2.0
)
```

---

## Behavioral Features

✅ Urgency-adjusted charging thresholds
✅ Time pressure calculation
✅ Charging strategy selection
✅ Speed adjustment for urgent appointments
✅ Destination priority ranking
✅ Integrated with StoppedState
✅ Compatible with TimeConstraintManager
✅ Configurable multipliers
✅ Comprehensive logging

---

## Validation Results

✅ All 5 Python files syntax-valid
✅ UrgencyModel methods tested
✅ StoppedState integration verified
✅ Scenario creation validated
✅ Demo script functional

---

## Status Summary

**Task 3: Urgency Modeling**
- ✅ Framework implementation (UrgencyModel class)
- ✅ StoppedState integration
- ✅ Scenario creation
- ✅ Validation demo
- ✅ Documentation

**Ready for production and next task.**

---

*Last Updated: Task 3 Complete*
*Next Action: Task 4 - Validation & Refinement*
