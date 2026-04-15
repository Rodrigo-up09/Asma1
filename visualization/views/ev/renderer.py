import pygame

WHITE = (255, 255, 255)
TEXT_DIM = (140, 140, 140)
EV_DRIVING = (52, 152, 219)
EV_GOING = (243, 156, 18)
EV_CHARGING = (241, 196, 15)
EV_WAITING = (155, 89, 182)
SOC_HIGH = (46, 204, 113)
SOC_LOW = (231, 76, 60)
TARGET_COLOURS = [
    (100, 180, 255),
    (255, 150, 200),
    (180, 255, 150),
    (255, 200, 100),
]


class EVRenderer:
    def __init__(self, world_to_screen):
        self.world_to_screen = world_to_screen

    def draw_all(self, surface, font, ev_agents):
        for ev in ev_agents:
            self.draw_ev(surface, font, ev)

        for index, ev in enumerate(ev_agents):
            self.draw_targets(surface, font, ev, index)

    def draw_ev(self, surface, font, ev):
        sx, sy = self.world_to_screen(ev.x, ev.y)
        state = self._ev_state(ev)
        name = str(ev.jid).split("@")[0]
        colour = self._state_colour(state)

        if state == "WAITING_QUEUE" and ev.current_cs_jid:
            cs_pos = ev._get_cs_position(ev.current_cs_jid)
            target_sx, target_sy = self.world_to_screen(cs_pos["x"], cs_pos["y"])
            queue_slot = abs(hash(str(ev.jid))) % 4
            sx = target_sx + 34 + queue_slot * 20
            sy = target_sy - 12 + queue_slot * 10

        if state == "GOING_TO_CHARGER" and ev.current_cs_jid:
            cs_pos = ev._get_cs_position(ev.current_cs_jid)
            target_sx, target_sy = self.world_to_screen(cs_pos["x"], cs_pos["y"])
            pygame.draw.line(surface, EV_GOING, (sx, sy), (target_sx, target_sy), 2)

        if state == "DRIVING" and hasattr(ev, "next_target"):
            target = ev.next_target()
            if target:
                tx, ty = self.world_to_screen(target["x"], target["y"])
                pygame.draw.line(surface, EV_DRIVING, (sx, sy), (tx, ty), 1)

        radius = 14
        pygame.draw.circle(surface, colour, (sx, sy), radius)
        pygame.draw.circle(surface, WHITE, (sx, sy), radius, 2)

        label = font.render(name, True, WHITE)
        surface.blit(label, (sx - label.get_width() // 2, sy - radius - 16))

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
                self._soc_colour(ev.current_soc),
                (bar_x, bar_y, fill_w, bar_h),
                border_radius=2,
            )

        soc_text = font.render(f"{ev.current_soc:.0%}", True, TEXT_DIM)
        surface.blit(soc_text, (sx - soc_text.get_width() // 2, bar_y + bar_h + 2))

    def draw_targets(self, surface, font, ev, index):
        if not hasattr(ev, "schedule") or not ev.schedule:
            return

        colour = TARGET_COLOURS[index % len(TARGET_COLOURS)]
        ev_name = str(ev.jid).split("@")[0]

        grouped = {}
        for stop in ev.schedule:
            key = (stop["name"], stop["x"], stop["y"])
            grouped.setdefault(key, []).append(stop["hour"])

        for (name, wx, wy), hours in grouped.items():
            tx, ty = self.world_to_screen(wx, wy)
            diamond = [
                (tx, ty - 7),
                (tx + 5, ty),
                (tx, ty + 7),
                (tx - 5, ty),
            ]
            pygame.draw.polygon(surface, colour, diamond)
            pygame.draw.polygon(surface, WHITE, diamond, 1)
            times_str = ", ".join(
                f"{int(h):02d}:{int((h % 1) * 60):02d}" for h in hours
            )
            label = font.render(f"{name} ({ev_name}) {times_str}", True, colour)
            surface.blit(label, (tx + 8, ty - 7))

    def _ev_state(self, ev):
        for behaviour in ev.behaviours:
            if hasattr(behaviour, "current_state"):
                return behaviour.current_state
        return "UNKNOWN"

    def _state_colour(self, state):
        if state == "CHARGING":
            return EV_CHARGING
        if state == "WAITING_QUEUE":
            return EV_WAITING
        if state == "GOING_TO_CHARGER":
            return EV_GOING
        return EV_DRIVING

    def _soc_colour(self, soc):
        r = int(SOC_LOW[0] + (SOC_HIGH[0] - SOC_LOW[0]) * soc)
        g = int(SOC_LOW[1] + (SOC_HIGH[1] - SOC_LOW[1]) * soc)
        b = int(SOC_LOW[2] + (SOC_HIGH[2] - SOC_LOW[2]) * soc)
        return (r, g, b)
