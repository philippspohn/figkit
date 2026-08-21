"""A small, dependency-free SVG path toolkit.

Enough to parse, transform, measure and flatten path data — which is what we
need for accurate bounding boxes, arrow geometry and embedding external SVGs.
"""

from __future__ import annotations

import math
import re

__all__ = [
    "parse_path", "abs_segments", "path_bbox", "transform_path_data",
    "translate_path_data", "scale_path_data", "flatten_path", "path_length",
    "point_at", "fmt", "path_from_points", "rounded_polyline",
]

_TOKEN_RE = re.compile(r"([MmZzLlHhVvCcSsQqTtAa])|(-?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)")

_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2,
         "A": 7, "Z": 0}


def fmt(v) -> str:
    """Compact number formatting for path/attribute output."""
    if isinstance(v, str):
        return v
    v = float(v)
    if v != v or v in (float("inf"), float("-inf")):
        return "0"
    if abs(v - round(v)) < 5e-5:
        return str(int(round(v)))
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s or "0"


def parse_path(d: str) -> list:
    """Tokenise path data into ``[(command, [numbers...]), ...]``.

    Repeated coordinate sets are expanded into separate commands, and an
    implicit ``L``/``l`` after ``M``/``m`` is made explicit.
    """
    if not d:
        return []
    out = []
    cmd = None
    nums: list = []
    for m in _TOKEN_RE.finditer(d):
        if m.group(1):
            if cmd is not None:
                out.extend(_emit(cmd, nums))
            cmd = m.group(1)
            nums = []
        else:
            nums.append(float(m.group(2)))
    if cmd is not None:
        out.extend(_emit(cmd, nums))
    return out


def _emit(cmd: str, nums: list) -> list:
    n = _ARGS[cmd.upper()]
    if n == 0:
        return [(cmd, [])]
    if not nums:
        return []
    out = []
    first = True
    for i in range(0, len(nums) - n + 1, n):
        c = cmd
        if not first and cmd in "Mm":
            c = "L" if cmd == "M" else "l"
        out.append((c, nums[i:i + n]))
        first = False
    return out


def abs_segments(d: str) -> list:
    """Normalise to absolute segments.

    Yields ``("M", x, y)``, ``("L", x, y)``, ``("C", x1,y1,x2,y2,x,y)``,
    ``("Q", x1,y1,x,y)`` and ``("Z",)``. Arcs are converted to cubics.
    """
    segs = []
    cx = cy = 0.0        # current point
    sx = sy = 0.0        # subpath start
    prev_c2 = None       # previous cubic control point (for S)
    prev_q1 = None       # previous quadratic control point (for T)
    for cmd, a in parse_path(d):
        up = cmd.upper()
        rel = cmd.islower()
        if up == "M":
            x, y = (cx + a[0], cy + a[1]) if rel else (a[0], a[1])
            segs.append(("M", x, y))
            cx, cy = sx, sy = x, y
            prev_c2 = prev_q1 = None
        elif up == "L":
            x, y = (cx + a[0], cy + a[1]) if rel else (a[0], a[1])
            segs.append(("L", x, y))
            cx, cy = x, y
            prev_c2 = prev_q1 = None
        elif up == "H":
            x = cx + a[0] if rel else a[0]
            segs.append(("L", x, cy))
            cx = x
            prev_c2 = prev_q1 = None
        elif up == "V":
            y = cy + a[0] if rel else a[0]
            segs.append(("L", cx, y))
            cy = y
            prev_c2 = prev_q1 = None
        elif up == "C":
            pts = [(cx + a[i] if rel else a[i], cy + a[i + 1] if rel else a[i + 1])
                   for i in (0, 2, 4)]
            segs.append(("C", pts[0][0], pts[0][1], pts[1][0], pts[1][1],
                         pts[2][0], pts[2][1]))
            prev_c2 = pts[1]
            cx, cy = pts[2]
            prev_q1 = None
        elif up == "S":
            c1 = (2 * cx - prev_c2[0], 2 * cy - prev_c2[1]) if prev_c2 else (cx, cy)
            pts = [(cx + a[i] if rel else a[i], cy + a[i + 1] if rel else a[i + 1])
                   for i in (0, 2)]
            segs.append(("C", c1[0], c1[1], pts[0][0], pts[0][1],
                         pts[1][0], pts[1][1]))
            prev_c2 = pts[0]
            cx, cy = pts[1]
            prev_q1 = None
        elif up == "Q":
            pts = [(cx + a[i] if rel else a[i], cy + a[i + 1] if rel else a[i + 1])
                   for i in (0, 2)]
            segs.append(("Q", pts[0][0], pts[0][1], pts[1][0], pts[1][1]))
            prev_q1 = pts[0]
            cx, cy = pts[1]
            prev_c2 = None
        elif up == "T":
            q1 = (2 * cx - prev_q1[0], 2 * cy - prev_q1[1]) if prev_q1 else (cx, cy)
            x, y = (cx + a[0], cy + a[1]) if rel else (a[0], a[1])
            segs.append(("Q", q1[0], q1[1], x, y))
            prev_q1 = q1
            cx, cy = x, y
            prev_c2 = None
        elif up == "A":
            rx, ry, rot, laf, sf = a[0], a[1], a[2], a[3], a[4]
            x, y = (cx + a[5], cy + a[6]) if rel else (a[5], a[6])
            segs.extend(_arc_to_cubics(cx, cy, rx, ry, rot, laf, sf, x, y))
            cx, cy = x, y
            prev_c2 = prev_q1 = None
        elif up == "Z":
            segs.append(("Z",))
            cx, cy = sx, sy
            prev_c2 = prev_q1 = None
    return segs


def _arc_to_cubics(x1, y1, rx, ry, rot_deg, large_arc, sweep, x2, y2) -> list:
    """Convert an SVG elliptical arc into a series of cubic segments."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [("L", x2, y2)]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rot_deg)
    cosp, sinp = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cosp * dx2 + sinp * dy2
    y1p = -sinp * dx2 + cosp * dy2
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = math.sqrt(max(0.0, num / den)) if den else 0.0
    if bool(large_arc) == bool(sweep):
        factor = -factor
    cxp = factor * rx * y1p / ry
    cyp = -factor * ry * x1p / rx
    cx = cosp * cxp - sinp * cyp + (x1 + x2) / 2.0
    cy = sinp * cxp + cosp * cyp + (y1 + y2) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        n = math.hypot(ux, uy) * math.hypot(vx, vy)
        if n == 0:
            return 0.0
        a = math.acos(max(-1.0, min(1.0, dot / n)))
        return -a if (ux * vy - uy * vx) < 0 else a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                   (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi

    n_segs = max(1, int(math.ceil(abs(dtheta) / (math.pi / 2))))
    delta = dtheta / n_segs
    t = 4.0 / 3.0 * math.tan(delta / 4.0)
    out = []
    th = theta1
    px = x1
    py = y1
    for _ in range(n_segs):
        cos1, sin1 = math.cos(th), math.sin(th)
        th2 = th + delta
        cos2, sin2 = math.cos(th2), math.sin(th2)
        ex = cx + rx * cosp * cos2 - ry * sinp * sin2
        ey = cy + rx * sinp * cos2 + ry * cosp * sin2
        d1x = -rx * cosp * sin1 - ry * sinp * cos1
        d1y = -rx * sinp * sin1 + ry * cosp * cos1
        d2x = -rx * cosp * sin2 - ry * sinp * cos2
        d2y = -rx * sinp * sin2 + ry * cosp * cos2
        out.append(("C", px + t * d1x, py + t * d1y,
                    ex - t * d2x, ey - t * d2y, ex, ey))
        px, py, th = ex, ey, th2
    return out


# --------------------------------------------------------------------------
# Bounding box (exact, using Bezier extrema)
# --------------------------------------------------------------------------

def _bez_extrema(p0, p1, p2, p3=None) -> list:
    """Parameter values where a Bezier component reaches an extremum."""
    ts = []
    if p3 is None:                    # quadratic
        den = p0 - 2 * p1 + p2
        if abs(den) > 1e-12:
            t = (p0 - p1) / den
            if 0 < t < 1:
                ts.append(t)
        return ts
    a = -p0 + 3 * p1 - 3 * p2 + p3
    b = 2 * (p0 - 2 * p1 + p2)
    c = p1 - p0
    if abs(a) < 1e-12:
        if abs(b) > 1e-12:
            t = -c / b
            if 0 < t < 1:
                ts.append(t)
        return ts
    disc = b * b - 4 * a * c
    if disc < 0:
        return ts
    sq = math.sqrt(disc)
    for t in ((-b + sq) / (2 * a), (-b - sq) / (2 * a)):
        if 0 < t < 1:
            ts.append(t)
    return ts


def _bez_at(t, p0, p1, p2, p3=None) -> float:
    if p3 is None:
        mt = 1 - t
        return mt * mt * p0 + 2 * mt * t * p1 + t * t * p2
    mt = 1 - t
    return (mt ** 3 * p0 + 3 * mt * mt * t * p1
            + 3 * mt * t * t * p2 + t ** 3 * p3)


def path_bbox(d: str) -> tuple:
    """Exact ``(x0, y0, x1, y1)`` bounds of path data (ignoring stroke width)."""
    xs: list = []
    ys: list = []
    cx = cy = 0.0
    sx = sy = 0.0
    started = False
    for seg in abs_segments(d):
        k = seg[0]
        if k == "M":
            cx, cy = seg[1], seg[2]
            sx, sy = cx, cy
            xs.append(cx)
            ys.append(cy)
            started = True
        elif k == "L":
            xs.extend((cx, seg[1]))
            ys.extend((cy, seg[2]))
            cx, cy = seg[1], seg[2]
        elif k == "C":
            x1, y1, x2, y2, x, y = seg[1:]
            xs.extend((cx, x))
            ys.extend((cy, y))
            for t in _bez_extrema(cx, x1, x2, x):
                xs.append(_bez_at(t, cx, x1, x2, x))
            for t in _bez_extrema(cy, y1, y2, y):
                ys.append(_bez_at(t, cy, y1, y2, y))
            cx, cy = x, y
        elif k == "Q":
            x1, y1, x, y = seg[1:]
            xs.extend((cx, x))
            ys.extend((cy, y))
            for t in _bez_extrema(cx, x1, x):
                xs.append(_bez_at(t, cx, x1, x))
            for t in _bez_extrema(cy, y1, y):
                ys.append(_bez_at(t, cy, y1, y))
            cx, cy = x, y
        elif k == "Z":
            cx, cy = sx, sy
    if not started or not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


# --------------------------------------------------------------------------
# Transforms
# --------------------------------------------------------------------------

def transform_path_data(d: str, affine) -> str:
    """Apply an :class:`~figkit.geom.Affine` to path data, returning new data."""
    if not d:
        return ""
    ap = affine.apply
    out = []
    for seg in abs_segments(d):
        k = seg[0]
        if k == "Z":
            out.append("Z")
            continue
        coords = seg[1:]
        pts = [ap((coords[i], coords[i + 1])) for i in range(0, len(coords), 2)]
        body = " ".join(f"{fmt(p.x)} {fmt(p.y)}" for p in pts)
        out.append(f"{k}{body}")
    return "".join(out)


def translate_path_data(d: str, dx: float, dy: float) -> str:
    from .geom import Affine
    if dx == 0 and dy == 0:
        return d
    return transform_path_data(d, Affine.translate(dx, dy))


def scale_path_data(d: str, sx: float, sy: float = None) -> str:
    from .geom import Affine
    sy = sx if sy is None else sy
    if sx == 1 and sy == 1:
        return d
    return transform_path_data(d, Affine.scale(sx, sy))


# --------------------------------------------------------------------------
# Flattening / measuring
# --------------------------------------------------------------------------

def flatten_path(d: str, steps: int = 16) -> list:
    """Approximate path data as a list of polylines (lists of ``(x, y)``)."""
    polys: list = []
    cur: list = []
    cx = cy = sx = sy = 0.0
    for seg in abs_segments(d):
        k = seg[0]
        if k == "M":
            if len(cur) > 1:
                polys.append(cur)
            cx, cy = seg[1], seg[2]
            sx, sy = cx, cy
            cur = [(cx, cy)]
        elif k == "L":
            cx, cy = seg[1], seg[2]
            cur.append((cx, cy))
        elif k == "C":
            x1, y1, x2, y2, x, y = seg[1:]
            for i in range(1, steps + 1):
                t = i / steps
                cur.append((_bez_at(t, cx, x1, x2, x), _bez_at(t, cy, y1, y2, y)))
            cx, cy = x, y
        elif k == "Q":
            x1, y1, x, y = seg[1:]
            for i in range(1, steps + 1):
                t = i / steps
                cur.append((_bez_at(t, cx, x1, x), _bez_at(t, cy, y1, y)))
            cx, cy = x, y
        elif k == "Z":
            cur.append((sx, sy))
            polys.append(cur)
            cx, cy = sx, sy
            cur = [(cx, cy)]
    if len(cur) > 1:
        polys.append(cur)
    return polys


def path_length(d: str, steps: int = 24) -> float:
    total = 0.0
    for poly in flatten_path(d, steps):
        for i in range(len(poly) - 1):
            total += math.hypot(poly[i + 1][0] - poly[i][0],
                                poly[i + 1][1] - poly[i][1])
    return total


def point_at(d: str, t: float, steps: int = 24) -> tuple:
    """``(point, unit_direction)`` at fraction ``t`` along the whole path."""
    from .geom import point_along
    pts: list = []
    for poly in flatten_path(d, steps):
        pts.extend(poly)
    if not pts:
        from .geom import Point
        return Point(0, 0), Point(1, 0)
    return point_along(pts, t)


# --------------------------------------------------------------------------
# Building path data
# --------------------------------------------------------------------------

def path_from_points(points, close: bool = False) -> str:
    from .geom import to_point
    pts = [to_point(p) for p in points]
    if not pts:
        return ""
    parts = [f"M{fmt(pts[0].x)} {fmt(pts[0].y)}"]
    parts += [f"L{fmt(p.x)} {fmt(p.y)}" for p in pts[1:]]
    if close:
        parts.append("Z")
    return "".join(parts)


def rounded_polyline(points, radius: float = 0.0, close: bool = False) -> str:
    """Polyline with rounded corners — the workhorse for elbow connectors."""
    from .geom import to_point
    pts = [to_point(p) for p in points]
    # drop consecutive duplicates
    clean = [pts[0]] if pts else []
    for p in pts[1:]:
        if abs(p.x - clean[-1].x) > 1e-9 or abs(p.y - clean[-1].y) > 1e-9:
            clean.append(p)
    pts = clean
    if len(pts) < 2:
        return path_from_points(pts, close)
    if radius <= 0:
        return path_from_points(pts, close)

    parts = []
    n = len(pts)
    idxs = range(n) if close else range(1, n - 1)
    if not close:
        parts.append(f"M{fmt(pts[0].x)} {fmt(pts[0].y)}")
    else:
        first_prev, first_cur = pts[-1], pts[0]
        v_in = (first_cur - first_prev)
        start = first_cur - v_in.normalized() * min(radius, v_in.length / 2)
        parts.append(f"M{fmt(start.x)} {fmt(start.y)}")

    for i in idxs:
        prev_p = pts[(i - 1) % n]
        cur = pts[i]
        nxt = pts[(i + 1) % n]
        v_in = cur - prev_p
        v_out = nxt - cur
        len_in, len_out = v_in.length, v_out.length
        if len_in < 1e-9 or len_out < 1e-9:
            continue
        u_in, u_out = v_in.normalized(), v_out.normalized()
        # collinear corner: nothing to round
        if abs(u_in.x * u_out.y - u_in.y * u_out.x) < 1e-6 and \
                (u_in.x * u_out.x + u_in.y * u_out.y) > 0:
            continue
        r = min(radius, len_in / 2.0, len_out / 2.0)
        a = cur - v_in.normalized() * r
        b = cur + v_out.normalized() * r
        parts.append(f"L{fmt(a.x)} {fmt(a.y)}")
        parts.append(f"Q{fmt(cur.x)} {fmt(cur.y)} {fmt(b.x)} {fmt(b.y)}")
    if close:
        parts.append("Z")
    else:
        parts.append(f"L{fmt(pts[-1].x)} {fmt(pts[-1].y)}")
    return "".join(parts)
