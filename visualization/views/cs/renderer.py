import pygame

WHITE = (255, 255, 255)
TEXT_COLOUR = (220, 220, 220)
TEXT_DIM = (140, 140, 140)
CS_COLOUR = (46, 204, 113)
CS_BORDER = (39, 174, 96)
PRICE_COLOUR = (255, 220, 100)
SOLAR_COLOUR = (255, 200, 90)


class CSRenderer:
    def __init__(self, world_to_screen):
        self.world_to_screen = world_to_screen

    def draw(self, surface, font, cs):
        sx, sy = self.world_to_screen(cs.x, cs.y)
        size = 22

        rect = pygame.Rect(sx - size, sy - size, size * 2, size * 2)
        pygame.draw.rect(surface, CS_COLOUR, rect, border_radius=5)
        pygame.draw.rect(surface, CS_BORDER, rect, width=2, border_radius=5)

        icon = font.render("C", True, WHITE)
        surface.blit(icon, (sx - icon.get_width() // 2, sy - icon.get_height() // 2))

        name = str(cs.jid).split("@")[0]
        label = font.render(name, True, TEXT_COLOUR)
        surface.blit(label, (sx - label.get_width() // 2, sy + size + 4))

        info = font.render(f"{cs.used_doors}/{cs.num_doors} doors", True, TEXT_DIM)
        surface.blit(info, (sx - info.get_width() // 2, sy + size + 18))

        price = getattr(cs, "electricity_price", 0.0)
        price_text = font.render(f"${price:.2f}/kWh", True, PRICE_COLOUR)
        surface.blit(price_text, (sx - price_text.get_width() // 2, sy + size + 32))

        solar_rate = getattr(cs, "solar_production_rate", 0.0)
        solar_text = font.render(f"Solar: {solar_rate:.1f} kW", True, SOLAR_COLOUR)
        surface.blit(solar_text, (sx - solar_text.get_width() // 2, sy + size + 46))
