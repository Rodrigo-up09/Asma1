# Agent Communications

## EV Agent → CS Agent

| Message             | Performative | Trigger                        | Body              | Purpose                                                                |
| :------------------ | :----------- | :----------------------------- | :---------------- | :--------------------------------------------------------------------- |
| **Charge Request**  | `request`    | SoC drops below `required_soc` | `request-charge`  | EV asks the CS for an available charging slot                          |
| **Charge Complete** | `inform`     | SoC reaches `required_soc`     | `charge-complete` | EV notifies CS that it has finished charging and the slot can be freed |

## CS Agent → EV Agent

| Message    | Performative | Trigger                                  | Body     | Purpose                                    |
| :--------- | :----------- | :--------------------------------------- | :------- | :----------------------------------------- |
| **Accept** | `agree`      | `active_sessions < num_charging_points`  | `accept` | CS confirms the charging slot is available |
| **Reject** | `refuse`     | `active_sessions >= num_charging_points` | `reject` | CS informs the EV that all slots are full  |

## Communication Flow

```
EV (DRIVING)                              CS (EMPTY / WORKING)
    │                                           │
    │  SoC ≤ required_soc                       │
    │──── request-charge ──────────────────────▶│
    │                                           │  check available slots
    │◀──────────────── accept ──────────────────│
    │                                           │  → WORKING
    │  → CHARGING                               │
    │  (SoC increases each tick)                │
    │                                           │
    │  SoC ≥ required_soc                       │
    │──── charge-complete ─────────────────────▶│
    │                                           │  free slot
    │  → DRIVING                                │  → EMPTY (if no other EVs)
    │                                           │
```

## EV Agent FSM States

| State              | Description                                                                                                                          |
| :----------------- | :----------------------------------------------------------------------------------------------------------------------------------- |
| `DRIVING`          | Draining battery each tick. When SoC ≤ `required_soc` → transitions to `GOING_TO_CHARGER`                                            |
| `GOING_TO_CHARGER` | Sends `request-charge` to CS. If accepted → `CHARGING`. If rejected → retries after 3s                                               |
| `CHARGING`         | Increases SoC each tick using `max_charge_rate_kw`. When SoC ≥ `required_soc` → sends `charge-complete` and transitions to `DRIVING` |

## CS Agent FSM States

| State     | Description                                                                                                                 |
| :-------- | :-------------------------------------------------------------------------------------------------------------------------- |
| `EMPTY`   | Waiting for incoming `request-charge` messages. Replies `accept`/`reject` based on slot availability                        |
| `WORKING` | Actively charging EVs. Handles both `charge-complete` (frees a slot) and new `request-charge` (accepts if capacity remains) |
