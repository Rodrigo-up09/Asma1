import asyncio
import json

import spade
from spade.agent import Agent
from spade.behaviour import FSMBehaviour, State
from spade.message import Message

# ──────────────────────────────────────────────
#  FSM States
# ──────────────────────────────────────────────
STATE_AVAILABLE = "AVAILABLE"  # Há portas disponíveis
STATE_FULL = "FULL"  # Sem portas disponíveis (fila de espera)


# ──────────────────────────────────────────────
#  FSM Behaviour
# ──────────────────────────────────────────────
class CSChargingFSM(FSMBehaviour):
    async def on_start(self):
        print(f"[FSM] Starting at state: {self.current_state}")

    async def on_end(self):
        print(f"[FSM] Finished at state: {self.current_state}")


# ──────────────────────────────────────────────
#  AVAILABLE State (há portas livres)
# ──────────────────────────────────────────────
class AvailableState(State):
    async def run(self):
        msg = await self.receive(timeout=5)

        if msg and msg.get_metadata("performative") == "request":
            await self.agent.handle_request(msg)

        # Transição para FULL se não há portas disponíveis
        if self.agent.used_doors >= self.agent.num_doors:
            self.set_next_state(STATE_FULL)
            return

        self.set_next_state(STATE_AVAILABLE)


# ──────────────────────────────────────────────
#  FULL State (sem portas disponíveis)
# ──────────────────────────────────────────────
class FullState(State):
    async def run(self):
        msg = await self.receive(timeout=1)

        if msg and msg.get_metadata("performative") == "request":
            await self.agent.handle_request(msg)

        # Processa a fila
        await self.agent.process_queue()

        # Se há portas disponíveis, volta a AVAILABLE
        if self.agent.used_doors < self.agent.num_doors:
            self.set_next_state(STATE_AVAILABLE)
            return

        self.set_next_state(STATE_FULL)


# ──────────────────────────────────────────────
#  Charging Station Agent
# ──────────────────────────────────────────────
class CSAgent(Agent):
    def __init__(self, jid, password, cs_config=None, *args, **kwargs):
        super().__init__(jid, password, *args, **kwargs)

        config = cs_config or {}

        # Station attributes
        self.max_charging_rate = config.get("max_charging_rate", 22.0)  # kW
        self.num_doors = config.get("num_doors", 4)
        self.capacity = config.get("capacity", 150.0)  # kWh disponíveis na rede
        self.used_doors = 0
        self.request_queue = []  # Lista de (ev_jid, required_energy, max_charging_rate)
        self.active_charging = {}  # {ev_jid: (required_energy, started_time)}

    def _parse_request(self, raw_body):
        """Parse e valida mensagem de request"""
        if not raw_body:
            return None
        try:
            data = json.loads(raw_body)
            required_energy = float(data.get("required_energy", 0))
            max_charging_rate = float(data.get("max_charging_rate", self.max_charging_rate))
            return {"required_energy": required_energy, "max_charging_rate": max_charging_rate}
        except (json.JSONDecodeError, ValueError):
            return None

    async def _send_response(self, to_jid, status):
        """Envia resposta: 'accept' ou 'wait'"""
        msg = Message(to=str(to_jid))
        msg.set_metadata("protocol", "ev-charging")
        msg.set_metadata("performative", "response")
        msg.body = json.dumps({"status": status})
        await self.send(msg)
        print(f"[CS] → {to_jid}: {status}")

    async def handle_request(self, msg):
        """Processa pedido do EV"""
        ev_jid = str(msg.sender).split("/")[0]
        request_data = self._parse_request(msg.body)

        if not request_data:
            return

        required_energy = request_data["required_energy"]
        max_charging_rate = request_data["max_charging_rate"]

        # Verifica se pode aceitar imediatamente (porta disponível + capacidade suficiente)
        if self.used_doors < self.num_doors and required_energy <= self.capacity:
            # Aceita o pedido
            self.used_doors += 1
            self.capacity -= required_energy
            self.active_charging[ev_jid] = {
                "required_energy": required_energy,
                "rate": max_charging_rate,
                "started_at": asyncio.get_event_loop().time(),
            }
            await self._send_response(ev_jid, "accept")
            print(f"[CS] ✓ Accepted {ev_jid}: {required_energy} kWh @ {max_charging_rate} kW | Doors: {self.used_doors}/{self.num_doors}")
        else:
            # Coloca na fila
            self.request_queue.append({
                "ev_jid": ev_jid,
                "required_energy": required_energy,
                "max_charging_rate": max_charging_rate,
            })
            await self._send_response(ev_jid, "wait")
            print(f"[CS] ⏳ Queued {ev_jid} | Queue size: {len(self.request_queue)}")

    async def process_queue(self):
        """Processa a fila e aceita pedidos se recursos disponíveis"""
        if not self.request_queue:
            return

        processed = []
        for i, req in enumerate(self.request_queue):
            ev_jid = req["ev_jid"]
            required_energy = req["required_energy"]
            rate = req["max_charging_rate"]

            # Se há porta e capacidade, aceita
            if self.used_doors < self.num_doors and required_energy <= self.capacity:
                self.used_doors += 1
                self.capacity -= required_energy
                self.active_charging[ev_jid] = {
                    "required_energy": required_energy,
                    "rate": rate,
                    "started_at": asyncio.get_event_loop().time(),
                }
                await self._send_response(ev_jid, "accept")
                print(f"[CS] ✓ Accepted (from queue) {ev_jid}: {required_energy} kWh | Doors: {self.used_doors}/{self.num_doors}")
                processed.append(i)

        # Remove processados da fila
        for idx in reversed(processed):
            self.request_queue.pop(idx)

    async def setup(self):
        print(f"[CS Agent] {self.jid} starting...")
        print(
            f"[CS Agent] Doors: {self.num_doors} | "
            f"Max charging rate: {self.max_charging_rate} kW | "
            f"Capacity: {self.capacity} kWh"
        )

        # Build the FSM
        fsm = CSChargingFSM()

        # Register states
        fsm.add_state(name=STATE_AVAILABLE, state=AvailableState(), initial=True)
        fsm.add_state(name=STATE_FULL, state=FullState())

        # Register transitions
        fsm.add_transition(source=STATE_AVAILABLE, dest=STATE_AVAILABLE)
        fsm.add_transition(source=STATE_AVAILABLE, dest=STATE_FULL)
        fsm.add_transition(source=STATE_FULL, dest=STATE_FULL)
        fsm.add_transition(source=STATE_FULL, dest=STATE_AVAILABLE)

        # Adiciona behavior SEM template específico (SPADE FSM tem problemas com Template personalizado)
        self.add_behaviour(fsm)


# ──────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────
async def main():
    cs = CSAgent(
        "cs1@localhost",
        "password",
        cs_config={
            "max_charging_rate": 22.0,
            "num_doors": 4,
            "capacity": 150.0,
        },
    )
    await cs.start()
    cs.web.start(hostname="127.0.0.1", port=10001)

    print("\nWeb interface: http://127.0.0.1:10001")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            break

    await cs.stop()


if __name__ == "__main__":
    spade.run(main())
