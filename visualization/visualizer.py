"""
Pygame 2-D world visualizer for the EV / CS multi-agent simulation.
Runs in its own thread so it does not block SPADE's asyncio loop.
"""

import os
import threading
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame


def _load_renderer(relative_path: str, class_name: str):
    module_path = Path(__file__).resolve().parent / relative_path
    spec = spec_from_file_location(class_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load renderer from {module_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


CSRenderer = _load_renderer("views/cs/renderer.py", "CSRenderer")
EVRenderer = _load_renderer("views/ev/renderer.py", "EVRenderer")
WorldRenderer = _load_renderer("views/world/renderer.py", "WorldRenderer")


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

        self.cs_renderer = CSRenderer(world_to_screen=self.world_to_screen)
        self.ev_renderer = EVRenderer(world_to_screen=self.world_to_screen)
        self.world_renderer = WorldRenderer(
            width=self.width,
            height=self.height,
            scale=self.scale,
        )

    # ── coordinate helpers ─────────────────────
    def world_to_screen(self, wx, wy):
        sx = int(self.offset_x + wx * self.scale)
        sy = int(self.offset_y - wy * self.scale)  # y flipped
        return sx, sy

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

        try:
            time_font = pygame.font.SysFont("dejavusans", 20, bold=True)
        except Exception:
            time_font = pygame.font.Font(None, 24)

        while not self._stop_event.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._stop_event.set()
                    break

            self.world_renderer.draw_background(screen)
            self.world_renderer.draw_grid(screen)

            for cs in self.cs_agents:
                self.cs_renderer.draw(screen, font, cs)

            self.ev_renderer.draw_all(screen, font, self.ev_agents)
            self.world_renderer.draw_legend(screen, font)
            self.world_renderer.draw_title(screen, font)

            # Draw building markers (one per unique location)
            buildings_seen = set()
            for ev in self.ev_agents:
                if hasattr(ev, "schedule") and ev.schedule:
                    for stop in ev.schedule:
                        key = (stop["name"], stop["x"], stop["y"])
                        if key not in buildings_seen:
                            buildings_seen.add(key)
                            name, wx, wy = key
                            tx, ty = self.world_to_screen(wx, wy)
                            diamond = [
                                (tx, ty - 7),
                                (tx + 5, ty),
                                (tx, ty + 7),
                                (tx - 5, ty),
                            ]
                            bld_colour = (180, 180, 220)
                            pygame.draw.polygon(screen, bld_colour, diamond)
                            pygame.draw.polygon(screen, WHITE, diamond, 1)
                            label = font.render(name, True, bld_colour)
                            screen.blit(label, (tx + 8, ty - 7))

            self._draw_legend(screen, font)

            # Title
            title = font.render("EV Charging Simulation", True, TEXT_COLOUR)
            screen.blit(title, (10, 8))

            # World clock display
            if self.world_clock:
                self.world_renderer.draw_time(screen, time_font, self.world_clock)

            pygame.display.flip()
            clock.tick(self.fps)

        pygame.quit()

    def stop(self):
        self._stop_event.set()

    def start_in_thread(self):
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return t


