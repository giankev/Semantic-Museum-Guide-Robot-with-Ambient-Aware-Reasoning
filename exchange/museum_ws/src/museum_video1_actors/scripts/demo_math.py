"""ROS-independent geometry and measurements for the one-actor experiment."""
import math


def yaw(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y*q.y + q.z*q.z))


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def alignment(raw, aligned):
    """Rigid world->odom transform from SAME-STAMP robot poses (x,y,yaw)."""
    a = wrap(aligned[2] - raw[2])
    c, s = math.cos(a), math.sin(a)
    return aligned[0] - c*raw[0] + s*raw[1], aligned[1] - s*raw[0] - c*raw[1], a


def transform(x, y, a):
    c, s = math.cos(a[2]), math.sin(a[2])
    return a[0] + c*x - s*y, a[1] + s*x + c*y


def rotate(x, y, angle):
    c, s = math.cos(angle), math.sin(angle)
    return c*x - s*y, s*x + c*y


def stamp_seconds(stamp):
    return stamp.sec + stamp.nanosec / 1e9


def speed_stats(samples):
    """Each sample is (sim_time, vx, vy). Never hide zeros or bad samples."""
    if not samples:
        return None
    speeds = [math.hypot(vx, vy) for _, vx, vy in samples]
    if any(not math.isfinite(s) for s in speeds):
        return {"samples": len(samples), "invalid": True}
    dt = [b[0] - a[0] for a, b in zip(samples, samples[1:])]
    accelerations = [math.hypot(b[1]-a[1], b[2]-a[2]) / (b[0]-a[0])
                     for a, b in zip(samples, samples[1:]) if b[0] > a[0]]
    return {"samples": len(speeds), "mean_mps": sum(speeds)/len(speeds),
            "min_mps": min(speeds), "max_mps": max(speeds),
            "above_0_10_percent": 100*sum(s > 0.10 for s in speeds)/len(speeds),
            "zero_samples": sum(s < 1e-6 for s in speeds),
            "over_1mps_samples": sum(s > 1.0 for s in speeds),
            "nonpositive_stamp_intervals": sum(d <= 0 for d in dt),
            "max_acceleration_mps2": max(accelerations, default=None),
            "sim_hz": (len(samples)-1)/(samples[-1][0]-samples[0][0])
            if len(samples) > 1 and samples[-1][0] > samples[0][0] else None,
            "max_gap_sim_s": max(dt, default=None)}
