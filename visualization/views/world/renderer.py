import pygame

GREY_BG = (30, 30, 35)
GRID_COLOUR = (50, 50, 55)
TEXT_COLOUR = (220, 220, 220)
EV_DRIVING = (52, 152, 219)
EV_GOING = (243, 156, 18)
EV_CHARGING = (241, 196, 15)
EV_WAITING = (155, 89, 182)
CS_COLOUR = (46, 204, 113)
TIME_COLOUR = (255, 220, 100)


class WorldRenderer:
    def __init__(self, width, height, scale):
        self.width = width
        self.height = height
        self.scale = scale

    def draw_background(self, surface):
        surface.fill(GREY_BG)

    def draw_grid(self, surface):
        step = int(self.scale * 5)
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
