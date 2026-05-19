import random
import time
import math

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
        if control is None:
            sx, sy = start
            ex, ey = end
            # midpoint
            mx, my = (sx + ex) / 2.0, (sy + ey) / 2.0
            # random perpendicular offset
            dx, dy = ex - sx, ey - sy
            # perpendicular vector
            px, py = -dy, dx
            norm = math.hypot(px, py) or 1.0
            ux, uy = px / norm, py / norm
            # magnitude depends on distance
            dist = math.hypot(dx, dy)
            magnitude = dist * random.uniform(0.08, 0.18)
            control = (int(mx + ux * magnitude), int(my + uy * magnitude))

        sx, sy = start
        cx, cy = control
        ex, ey = end

        points = []
        for i in range(steps + 1):
            t = i / float(steps)
            # Quadratic Bezier formula
            x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t ** 2 * ex
            y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t ** 2 * ey
            points.append((int(round(x)), int(round(y))))
        return points
