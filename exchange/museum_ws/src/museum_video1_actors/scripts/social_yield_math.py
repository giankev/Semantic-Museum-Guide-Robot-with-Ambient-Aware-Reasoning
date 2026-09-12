"""Forward-corridor social yielding; simulation HRI, not collision certification."""
import math


class YieldPolicy:
    def __init__(self, config):
        self.config = config
        self.yielding = False
        self.clear_since = None

    def update(self, now, people, robot_speed):
        c = self.config
        relevant = []
        stop, hold = False, False
        for name, x, y, vx, vy in people:
            if not all(math.isfinite(v) for v in (x, y, vx, vy)):
                raise ValueError('Nonfinite relative person state')
            if x <= 0:  # A close person behind the robot is not a forward conflict.
                continue
            entry = 0.0 if abs(y) <= c['corridor_half_width'] else math.inf
            if entry and y*vy < 0:
                entry = (math.copysign(c['corridor_half_width'], y)-y)/vy
            px = x + (vx-robot_speed)*entry if math.isfinite(entry) else x
            approaching = 0 <= entry <= c['prediction_horizon'] and 0 < px < c['slow_distance']
            if approaching:
                relevant.append((name, math.hypot(x, y), px, entry))
                stop |= px <= c['stop_distance'] and entry <= c['stop_horizon']
            hold |= (x < c['release_distance'] and abs(y) < c['release_half_width']) or (
                approaching and px < c['release_distance'] and entry < c['stop_horizon'])
        if stop:
            self.yielding, self.clear_since = True, None
        if self.yielding:
            if hold:
                self.clear_since = None
            elif self.clear_since is None:
                self.clear_since = now
            elif now-self.clear_since >= c['clear_time']:
                self.yielding, self.clear_since = False, None
        nearest = min(relevant, key=lambda p: p[1]) if relevant else None
        factor = min((max(.15, min(1., (p[2]-c['stop_distance']) /
                     (c['slow_distance']-c['stop_distance']))) for p in relevant), default=1.)
        state = 'YIELDING' if self.yielding else ('SLOW' if factor < .99 else 'CLEAR')
        return dict(state=state, scale=0. if self.yielding else factor,
                    nearest_person=nearest[0] if nearest else None,
                    distance=nearest[1] if nearest else None)
