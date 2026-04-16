import pygame
import math

GREY_BG = (30, 30, 35)
GRID_COLOUR = (50, 50, 55)
TEXT_COLOUR = (220, 220, 220)
EV_DRIVING = (52, 152, 219)
EV_GOING = (243, 156, 18)
EV_CHARGING = (241, 196, 15)
EV_WAITING = (155, 89, 182)
CS_COLOUR = (46, 204, 113)
TIME_COLOUR = (255, 220, 100)
SUN_GRID_TINT = (255, 248, 190)

# Visual-only solar windows (do not affect WorldModel logic).
VISUAL_SUN_START_HOUR = 3.5
VISUAL_DAY_START_HOUR = 5.0
VISUAL_DAY_END_HOUR = 20.0
VISUAL_SUN_END_HOUR = 21.5


class WorldRenderer:
    def __init__(self, width, height, scale):
        self.width = width
        self.height = height
        self.scale = scale

    def draw_background(self, surface):
        surface.fill(GREY_BG)

    @staticmethod
    def _is_visual_sun_active(hour: float) -> bool:
        return VISUAL_SUN_START_HOUR <= hour < VISUAL_SUN_END_HOUR

    @staticmethod
    def _daylight_progress(hour: float) -> float:
        day_start = VISUAL_DAY_START_HOUR
        day_end = VISUAL_DAY_END_HOUR
        span = day_end - day_start
        if span <= 0.0:
            return 0.0
        progress = (hour - day_start) / span
        return min(1.0, max(0.0, progress))

    @staticmethod
    def _visual_sun_strength(hour: float) -> float:
        """Return visual sunlight strength [0,1] with smooth dawn/dusk ramps."""
        if hour < VISUAL_SUN_START_HOUR or hour >= VISUAL_SUN_END_HOUR:
            return 0.0

        # Dawn ramp: gradually increase before the real daylight window.
        if VISUAL_SUN_START_HOUR <= hour < VISUAL_DAY_START_HOUR:
            span = VISUAL_DAY_START_HOUR - VISUAL_SUN_START_HOUR
            if span <= 0.0:
                return 0.0
            # Ease-in to avoid abrupt sunrise tinting.
            progress = (hour - VISUAL_SUN_START_HOUR) / span
            return progress * progress

        # Core daytime visual strength.
        if VISUAL_DAY_START_HOUR <= hour < VISUAL_DAY_END_HOUR:
            return 1.0

        # Dusk ramp: gradually decrease after the real daylight window.
        span = VISUAL_SUN_END_HOUR - VISUAL_DAY_END_HOUR
        if span <= 0.0:
            return 0.0
        progress = 1.0 - ((hour - VISUAL_DAY_END_HOUR) / span)
        return progress * progress

    @staticmethod
    def _sun_spread_factor(global_strength: float) -> float:
        """Control how much map area is illuminated as the sun ramps in/out.

        At low strength (early dawn / late dusk), keep sunlight focused in a
        smaller area. As strength increases, expand coverage smoothly.
        """
        strength = min(1.0, max(0.0, global_strength))
        return 0.28 + (0.72 * strength)

    def _screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        wx = (sx - (self.width / 2.0)) / self.scale
        wy = ((self.height / 2.0) - sy) / self.scale
        return wx, wy

    def _visible_world_bounds(self) -> tuple[float, float, float, float]:
        half_w = self.width / (2.0 * self.scale)
        half_h = self.height / (2.0 * self.scale)
        return -half_w, half_w, -half_h, half_h

    def _sun_world_position(self, hour: float) -> tuple[float, float] | None:
        if not self._is_visual_sun_active(hour):
            return None
        min_x, max_x, _min_y, max_y = self._visible_world_bounds()
        progress = self._daylight_progress(hour)
        sun_x = min_x + progress * (max_x - min_x)
        sun_y = max_y / 2.0
        return sun_x, sun_y

    def _light_intensity(
        self,
        wx: float,
        wy: float,
        sun_x: float,
        sun_y: float,
        spread_factor: float = 1.0,
    ) -> float:
        min_x, max_x, _min_y, _max_y = self._visible_world_bounds()
        width = max(1.0, max_x - min_x)
        sigma = max(1.0, 0.30 * width * max(0.15, spread_factor))
        distance = math.hypot(wx - sun_x, wy - sun_y)
        intensity = math.exp(-((distance ** 2) / (2.0 * (sigma ** 2))))
        return min(1.0, max(0.0, intensity))

    def _draw_sunlight_overlay(self, surface, hour: float, step: int):
        sun_pos = self._sun_world_position(hour)
        if sun_pos is None:
            return

        global_strength = self._visual_sun_strength(hour)
        if global_strength <= 0.0:
            return

        sun_x, sun_y = sun_pos
        spread_factor = self._sun_spread_factor(global_strength)
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        for x in range(0, self.width, step):
            for y in range(0, self.height, step):
                cx = x + step / 2.0
                cy = y + step / 2.0
                wx, wy = self._screen_to_world(cx, cy)
                intensity = self._light_intensity(
                    wx,
                    wy,
                    sun_x,
                    sun_y,
                    spread_factor=spread_factor,
                )

                # Extra easing on intensity at dawn/dusk to avoid abrupt spread.
                effective_intensity = (intensity ** 1.5) * (global_strength ** 1.35)
                if effective_intensity < 0.07:
                    continue

                # Very light yellow so agents and labels stay readable.
                alpha = int(6 + 44 * effective_intensity)
                colour = (*SUN_GRID_TINT, alpha)
                pygame.draw.rect(overlay, colour, (x, y, step, step))

        surface.blit(overlay, (0, 0))

    def draw_grid(self, surface, world_clock=None):
        step = int(self.scale * 5)

        if world_clock is not None:
            self._draw_sunlight_overlay(surface, world_clock.current_hour(), step)

        for x in range(0, self.width, step):
            pygame.draw.line(surface, GRID_COLOUR, (x, 0), (x, self.height))
        for y in range(0, self.height, step):
            pygame.draw.line(surface, GRID_COLOUR, (0, y), (self.width, y))

    def draw_legend(self, surface, font):
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

    def draw_title(self, surface, font):
        title = font.render("EV Charging Simulation", True, TEXT_COLOUR)
        surface.blit(title, (10, 8))

    def draw_time(self, surface, time_font, world_clock):
        time_str = world_clock.formatted_time()
        time_surface = time_font.render(time_str, True, TIME_COLOUR)
        surface.blit(time_surface, (self.width - time_surface.get_width() - 14, 8))
