## II. Functionalities

### Possible Agents

* **Electric Vehicle (EV) Agent**
    Each electric vehicle is represented by an agent. The agent decides when to start charging, how long to charge, and at what power level, based on:
    * Battery state and required **State of Charge (SoC)**.
    * Departure time.
    * Electricity prices and grid conditions.
    
    Each EV agent **autonomously** manages its charging strategy while ensuring user mobility requirements are met. Agents coordinate with one another to avoid simultaneous peak charging and reduce congestion at charging stations.

* **Charging Station Agent**
    Each charging station is represented by an agent responsible for managing available charging points and enforcing power capacity constraints.
    * **Allocation:** It allocates charging slots among EV agents.
    * **Coordination:** It manages charging rates to prevent overload situations.
    * **Negotiation:** It may participate in negotiation processes when demand exceeds available infrastructure capacity.

* **World Agent**
    If necessary, and primarily for **information visualization**, a World agent can be included. This agent does not make decisions; it maintains global knowledge of the system and displays real-time information.

---

### Other Remarks

* **Dynamic Environment:** The simulation includes dynamic electricity prices (higher during peak hours, lower during off-peak) and dynamic arrival/departure patterns for electric vehicles.
* **Decentralized Decision-Making:** The system lacks a central controller. Each agent makes independent decisions and communicates with others to optimize charging coordination.
* **Collaboration:** Agents negotiate to balance demand. For example, vehicles with urgent departures may be prioritized, while flexible sessions are shifted to avoid high-price or high-load periods.
* **Renewable Energy and Storage:** Agents prioritize charging during periods of high renewable generation to reduce reliance on grid electricity.



---

## III. Expected Results

The system should track the following metrics to evaluate performance:

| Metric | Description |
| :--- | :--- |
| **Total Energy Consumption** | The aggregate energy used by all agents in the system. |
| **Total Charging Cost** | Total cost calculated based on dynamic pricing. |
| **Peak Load Reduction** | Efficiency in smoothing out demand spikes. |
| **SoC Success Rate** | Percentage of EVs reaching required charge before departure. |
| **Average Waiting Time** | The mean time EVs wait for an available charging slot. |
| **Renewable Utilization** | Amount of renewable energy used versus grid energy. |