import random
import time

class Humanize:
    def __init__(self, settings):
        self.jitter_radius = settings.get("jitter", {}).get("radius", 5)

    def get_jittered_coords(self, x, y):
        jx = x + random.randint(-self.jitter_radius, self.jitter_radius)
        jy = y + random.randint(-self.jitter_radius, self.jitter_radius)
        return jx, jy

    def get_random_delay(self, min_delay, max_delay):
        return random.uniform(min_delay, max_delay)

    def bezier_curve(self, start, end, control, steps=10):
        # Dummy bezier
        return []
