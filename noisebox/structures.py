"""Geometry of scenario structures (buildings, barriers, enclosures). Plain Python, no arcpy, no acoustics.

Coordinates are metres in the analysis coordinate system. Azimuths and orientations are in degrees clockwise from grid
north (map up): azimuth 0 points to +y, 90 to +x.
"""
import math

EPS = 1e-9
MAX_VERTICES = 400


# ------------------------------------------------------------------ rings
def clean_ring(pts):
    """Drop the closing vertex and consecutive duplicates. -> list of (x, y) floats."""
    out = []
    for p in pts or []:
        q = (float(p[0]), float(p[1]))
        if not out or math.hypot(q[0] - out[-1][0], q[1] - out[-1][1]) > 1e-9:
            out.append(q)
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1e-9:
        out.pop()
    return out


def signed_area(ring):
    a = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def ring_area(ring):
    return abs(signed_area(ring))


def point_in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def _seg_intersection(p1, p2, p3, p4):
    d1 = (p2[0] - p1[0], p2[1] - p1[1])
    d2 = (p4[0] - p3[0], p4[1] - p3[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < EPS:
        return None
    t = ((p3[0] - p1[0]) * d2[1] - (p3[1] - p1[1]) * d2[0]) / den
    u = ((p3[0] - p1[0]) * d1[1] - (p3[1] - p1[1]) * d1[0]) / den
    if 1e-9 < t < 1 - 1e-9 and 1e-9 < u < 1 - 1e-9:
        return (p1[0] + t * d1[0], p1[1] + t * d1[1])
    return None


def self_intersection(ring):
    """First point where two non-adjacent edges cross, or None."""
    n = len(ring)
    for i in range(n):
        a1, a2 = ring[i], ring[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            b1, b2 = ring[j], ring[(j + 1) % n]
            pt = _seg_intersection(a1, a2, b1, b2)
            if pt:
                return pt
    return None


def bbox_of(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def dist_point_segment(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 < EPS:
        return math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def dist_point_ring(px, py, ring):
    return min(dist_point_segment(px, py, ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring)))


def min_width(ring):
    """Smallest extent of the ring over a sweep of directions (a measure of how narrow it is), m."""
    best = float("inf")
    for k in range(0, 180, 5):
        a = math.radians(k)
        c, s = math.cos(a), math.sin(a)
        v = [x * c + y * s for x, y in ring]
        best = min(best, max(v) - min(v))
    return best


# ------------------------------------------------------------------ barriers
def azimuth_vec(az_deg):
    a = math.radians(az_deg)
    return math.sin(a), math.cos(a)


def barrier_from_placement(start, length, azimuth_deg):
    """Straight barrier from a start point, length and azimuth -> [start, end]."""
    ux, uy = azimuth_vec(azimuth_deg)
    return [(float(start[0]), float(start[1])),
            (float(start[0]) + length * ux, float(start[1]) + length * uy)]


def path_length(path):
    return sum(math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]) for i in range(len(path) - 1))


def clean_path(pts):
    out = []
    for p in pts or []:
        q = (float(p[0]), float(p[1]))
        if not out or math.hypot(q[0] - out[-1][0], q[1] - out[-1][1]) > 1e-9:
            out.append(q)
    return out


def densify(path, step):
    """Points along a polyline at most `step` apart (always includes every vertex)."""
    out = [path[0]]
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        n = max(1, int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / step)))
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    return out


def barrier_obstacles(path, definition, material=None, gap=None):
    """One engine obstacle per segment (a thin wall = 2 vertices).

    definition: {"mode": "relative", "value": h}  -> engine 'h' (flat top at highest ground under the segment + h)
                {"mode": "absolute", "value": z}  -> engine 'top' (absolute elevation of the top edge)
    """
    obs = []
    for i in range(len(path) - 1):
        o = {"x": [path[i][0], path[i + 1][0]], "y": [path[i][1], path[i + 1][1]],
             "h": None, "top": None, "gap": gap, "mat": material}
        if definition["mode"] == "absolute":
            o["top"] = float(definition["value"])
        else:
            o["h"] = float(definition["value"])
        obs.append(o)
    return obs


def building_obstacle(ring, height):
    return {"x": [p[0] for p in ring], "y": [p[1] for p in ring], "h": float(height), "top": None, "gap": None,
            "mat": None}


# ------------------------------------------------------------------ enclosures
def rect_footprint(center, length, width, orientation_deg):
    """Rectangle with its LENGTH along `orientation_deg` (clockwise from north), centred on `center` -> 4 corners."""
    ux, uy = azimuth_vec(orientation_deg)
    vx, vy = -uy, ux            # perpendicular (width direction)
    hl, hw = length / 2.0, width / 2.0
    cx, cy = center
    return [(cx - hl * ux - hw * vx, cy - hl * uy - hw * vy), (cx + hl * ux - hw * vx, cy + hl * uy - hw * vy),
            (cx + hl * ux + hw * vx, cy + hl * uy + hw * vy), (cx - hl * ux + hw * vx, cy - hl * uy + hw * vy)]


def compass(dx, dy):
    ang = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
    names = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return names[int((ang + 22.5) // 45) % 8]


def enclosure_faces(ring, height):
    """Radiating faces of an enclosure: one wall per footprint edge plus the roof. The floor is ground.

    -> list of dict(name, kind 'wall'|'roof', area m2, p1, p2). Wall names carry the compass direction the wall faces.
    """
    ring = clean_ring(ring)
    sgn = 1.0 if signed_area(ring) > 0 else -1.0       # counter-clockwise (+) means outward normal is the right-hand side
    faces = []
    used = {}
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        ex, ey = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = ey * sgn, -ex * sgn                    # outward normal
        nm = "Wall " + compass(nx, ny)
        used[nm] = used.get(nm, 0) + 1
        if used[nm] > 1:
            nm = "%s (%d)" % (nm, used[nm])
        faces.append({"name": nm, "kind": "wall", "area": L * height, "p1": a, "p2": b})
    faces.append({"name": "Roof", "kind": "roof", "area": ring_area(ring), "p1": None, "p2": None})
    return faces


# ------------------------------------------------------------------ sampling a gridded surface along a path
def profile_along(path, sample, step):
    """[(s, x, y, z)] along a polyline; `sample(x, y)` returns z or None."""
    pts = densify(path, step)
    out = []
    s = 0.0
    for i, p in enumerate(pts):
        if i:
            s += math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1])
        out.append((s, p[0], p[1], sample(p[0], p[1])))
    return out
