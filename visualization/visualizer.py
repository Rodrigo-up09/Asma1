"""
Pygame 2-D world visualizer for the EV / CS multi-agent simulation.
Runs in its own thread so it does not block SPADE's asyncio loop.
"""

import math
import os
import threading

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

# ── Colours ────────────────────────────────────
WHITE = (255, 255, 255)
GREY_BG = (30, 30, 35)
GRID_COLOUR = (50, 50, 55)
TEXT_COLOUR = (220, 220, 220)
TEXT_DIM = (140, 140, 140)

CS_COLOUR = (46, 204, 113)  # green
CS_BORDER = (39, 174, 96)

EV_DRIVING = (52, 152, 219)  # blue
EV_GOING = (243, 156, 18)  # orange
EV_CHARGING = (241, 196, 15)  # yellow
EV_WAITING = (155, 89, 182)  # purple

SOC_HIGH = (46, 204, 113)  # green
SOC_LOW = (231, 76, 60)  # red

LINE_COLOUR = (243, 156, 18, 120)  # semi-transparent orange


def _soc_colour(soc: float):
    """Interpolate green→red based on SoC (1.0 = green, 0.0 = red)."""
    r = int(SOC_LOW[0] + (SOC_HIGH[0] - SOC_LOW[0]) * soc)
    g = int(SOC_LOW[1] + (SOC_HIGH[1] - SOC_LOW[1]) * soc)
    b = int(SOC_LOW[2] + (SOC_HIGH[2] - SOC_LOW[2]) * soc)
    return (r, g, b)


class WorldVisualizer:
    """Real-time Pygame visualisation of the EV charging world."""

    def __init__(
        self,
        ev_agents,
        cs_agents,
        world_clock=None,
        width=900,
        height=700,
        scale=18.0,
        fps=30,
    ):
        self.ev_agents = ev_agents
        self.cs_agents = cs_agents
        self.world_clock = world_clock
        self.width = width
        self.height = height
        self.scale = scale
        self.fps = fps
        self._stop_event = threading.Event()

        # Offset so (0,0) in world coords is roughly centred on screen
        self.offset_x = width // 2
        self.offset_y = height // 2

    # ── coordinate helpers ─────────────────────
    def world_to_screen(self, wx, wy):
        sx = int(self.offset_x + wx * self.scale)
        sy = int(self.offset_y - wy * self.scale)  # y flipped
        return sx, sy

    # ── drawing ────────────────────────────────
    def _draw_grid(self, surface):
        step = int(self.scale * 5)  # grid every 5 world-units
        for x in range(0, self.width, step):
            pygame.draw.line(surface, GRID_COLOUR, (x, 0), (x, self.height))
        for y in range(0, self.height, step):
            pygame.draw.line(surface, GRID_COLOUR, (0, y), (self.width, y))

    def _draw_cs(self, surface, font, cs):
        sx, sy = self.world_to_screen(cs.x, cs.y)
        size = 22

        # Station square
        rect = pygame.Rect(sx - size, sy - size, size * 2, size * 2)
        pygame.draw.rect(surface, CS_COLOUR, rect, border_radius=5)
        pygame.draw.rect(surface, CS_BORDER, rect, width=2, border_radius=5)

        # ⚡ icon
        bolt = font.render("⚡", True, WHITE)
        surface.blit(bolt, (sx - bolt.get_width() // 2, sy - bolt.get_height() // 2))

        # Label
        name = str(cs.jid).split("@")[0]
        label = font.render(name, True, TEXT_COLOUR)
        surface.blit(label, (sx - label.get_width() // 2, sy + size + 4))

        # Doors info
        info = font.render(f"{cs.used_doors}/{cs.num_doors} doors", True, TEXT_DIM)
        surface.blit(info, (sx - info.get_width() // 2, sy + size + 18))

    def _ev_state(self, ev):
        """Best-effort FSM state detection."""
        # Check if there is an active behaviour with current_state
        for b in ev.behaviours:
            if hasattr(b, "current_state"):
                return b.current_state
        return "UNKNOWN"

    def _draw_ev(self, surface, font, ev):
        sx, sy = self.world_to_screen(ev.x, ev.y)
        state = self._ev_state(ev)
        name = str(ev.jid).split("@")[0]

        # Pick colour by state
        if state == "CHARGING":
            colour = EV_CHARGING
        elif state == "WAITING_QUEUE":
            colour = EV_WAITING
        elif state == "GOING_TO_CHARGER":
            colour = EV_GOING
        else:
            colour = EV_DRIVING

        # Show waiting EVs beside their target CS, not at their world position.
        if state == "WAITING_QUEUE" and ev.current_cs_jid:
            cs_pos = ev._get_cs_position(ev.current_cs_jid)
            target_sx, target_sy = self.world_to_screen(cs_pos["x"], cs_pos["y"])
            queue_slot = abs(hash(str(ev.jid))) % 4
            sx = target_sx + 34 + queue_slot * 20
            sy = target_sy - 12 + queue_slot * 10

        # Draw line to target CS if heading there
        if state == "GOING_TO_CHARGER" and ev.current_cs_jid:
            cs_pos = ev._get_cs_position(ev.current_cs_jid)
            target_sx, target_sy = self.world_to_screen(cs_pos["x"], cs_pos["y"])
            pygame.draw.line(surface, EV_GOING, (sx, sy), (target_sx, target_sy), 2)

        # Car circle
        radius = 14
        pygame.draw.circle(surface, colour, (sx, sy), radius)
        pygame.draw.circle(surface, WHITE, (sx, sy), radius, 2)

        # Name label
        label = font.render(name, True, WHITE)
        surface.blit(label, (sx - label.get_width() // 2, sy - radius - 16))

        # SoC bar
        bar_w = 30
        bar_h = 6
        bar_x = sx - bar_w // 2
        bar_y = sy + radius + 4
        pygame.draw.rect(
            surface, (60, 60, 60), (bar_x, bar_y, bar_w, bar_h), border_radius=2
        )
        fill_w = int(bar_w * ev.current_soc)
        if fill_w > 0:
            pygame.draw.rect(
                surface,
                _soc_colour(ev.current_soc),
                (bar_x, bar_y, fill_w, bar_h),
                border_radius=2,
            )

        # SoC percentage text
        soc_text = font.render(f"{ev.current_soc:.0%}", True, TEXT_DIM)
        surface.blit(soc_text, (sx - soc_text.get_width() // 2, bar_y + bar_h + 2))

    def _draw_legend(self, surface, font):
        x, y = 10, self.height - 110
        items = [
            (EV_DRIVING, "Driving"),
            (EV_GOING, "Going to charger"),
            (EV_WAITING, "Waiting queue"),
            (EV_CHARGING, "Charging"),
            (CS_COLOUR, "Charging station"),
        ]
        for colour, label in items:
            pygame.draw.circle(surface, colour, (x + 6, y + 6), 6)
            text = font.render(label, True, TEXT_COLOUR)
            surface.blit(text, (x + 18, y - 1))
            y += 20

    # ── main loop (runs in thread) ─────────────
    def run(self):
        pygame.init()
        screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("EV Charging World")
        clock = pygame.time.Clock()

        try:
            font = pygame.font.SysFont("dejavusans", 13)
        except Exception:
            font = pygame.font.Font(None, 16)

        while not self._stop_event.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._stop_event.set()
                    break

            screen.fill(GREY_BG)
            self._draw_grid(screen)

            for cs in self.cs_agents:
                self._draw_cs(screen, font, cs)

            for ev in self.ev_agents:
                self._draw_ev(screen, font, ev)

            self._draw_legend(screen, font)

            # Title
            title = font.render("EV Charging Simulation", True, TEXT_COLOUR)
            screen.blit(title, (10, 8))

            # World clock display
            if self.world_clock:
                try:
                    time_font = pygame.font.SysFont("dejavusans", 20, bold=True)
                except Exception:
                    time_font = pygame.font.Font(None, 24)
                time_str = self.world_clock.formatted_day_time()
                time_surface = time_font.render(time_str, True, (255, 220, 100))
                screen.blit(
                    time_surface, (self.width - time_surface.get_width() - 14, 8)
                )

            pygame.display.flip()
            clock.tick(self.fps)

        pygame.quit()

    def stop(self):
        self._stop_event.set()

    def start_in_thread(self):
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return t
