"""Geometry primitives: points, boxes, affine transforms."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

__all__ = [
    "Point",
    "BBox",
    "Affine",
    "ANCHOR_NAMES",
    "to_point",
    "deg2rad",
]

ANCHOR_NAMES = (
    "nw", "n", "ne",
    "w", "center", "e",
    "sw", "s", "se",
)

# Fractional (u, v) position inside a bbox for each named anchor.
_ANCHOR_UV = {
    "nw": (0.0, 0.0), "n": (0.5, 0.0), "ne": (1.0, 0.0),
    "w": (0.0, 0.5), "center": (0.5, 0.5), "c": (0.5, 0.5), "e": (1.0, 0.5),
    "sw": (0.0, 1.0), "s": (0.5, 1.0), "se": (1.0, 1.0),
    # friendly aliases
    "top": (0.5, 0.0), "bottom": (0.5, 1.0),
    "left": (0.0, 0.5), "right": (1.0, 0.5),
    "topleft": (0.0, 0.0), "topright": (1.0, 0.0),
    "bottomleft": (0.0, 1.0), "bottomright": (1.0, 1.0),
}

_OPPOSITE = {
    "n": "s", "s": "n", "e": "w", "w": "e",
    "ne": "sw", "sw": "ne", "nw": "se", "se": "nw",
    "center": "center",
}

# Outward unit normal for each side anchor (SVG axes: +y is down).
_ANCHOR_NORMAL = {
    "n": (0.0, -1.0), "s": (0.0, 1.0), "e": (1.0, 0.0), "w": (-1.0, 0.0),
    "ne": (0.7071, -0.7071), "nw": (-0.7071, -0.7071),
    "se": (0.7071, 0.7071), "sw": (-0.7071, 0.7071),
    "center": (0.0, 0.0),
}


def deg2rad(deg: float) -> float:
    return deg * math.pi / 180.0


@dataclass(frozen=True)
class Point:
    """An immutable 2D point. Supports +, -, * and tuple unpacking."""

    x: float
    y: float

    # -- construction ---------------------------------------------------
    @staticmethod
    def of(obj) -> "Point":
        return to_point(obj)

    # -- arithmetic -----------------------------------------------------
    def __add__(self, other) -> "Point":
        if isinstance(other, (int, float)):
            return Point(self.x + other, self.y + other)
        o = to_point(other)
        return Point(self.x + o.x, self.y + o.y)

    __radd__ = __add__

    def __sub__(self, other) -> "Point":
        if isinstance(other, (int, float)):
            return Point(self.x - other, self.y - other)
        o = to_point(other)
        return Point(self.x - o.x, self.y - o.y)

    def __rsub__(self, other) -> "Point":
        o = to_point(other)
        return Point(o.x - self.x, o.y - self.y)

    def __mul__(self, k: float) -> "Point":
        return Point(self.x * k, self.y * k)

    __rmul__ = __mul__

    def __truediv__(self, k: float) -> "Point":
        return Point(self.x / k, self.y / k)

    def __neg__(self) -> "Point":
        return Point(-self.x, -self.y)

    def __iter__(self):
        yield self.x
        yield self.y

    def __getitem__(self, i: int) -> float:
        return (self.x, self.y)[i]

    def __len__(self) -> int:
        return 2

    # -- vector helpers -------------------------------------------------
    @property
    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Point":
        n = self.length
        return Point(0.0, 0.0) if n == 0 else Point(self.x / n, self.y / n)

    def dot(self, other) -> float:
        o = to_point(other)
        return self.x * o.x + self.y * o.y

    def perp(self) -> "Point":
        """Rotate 90 degrees counter-clockwise on screen."""
        return Point(self.y, -self.x)

    def rotated(self, deg: float, about=(0.0, 0.0)) -> "Point":
        c, s = math.cos(deg2rad(deg)), math.sin(deg2rad(deg))
        o = to_point(about)
        dx, dy = self.x - o.x, self.y - o.y
        return Point(o.x + dx * c - dy * s, o.y + dx * s + dy * c)

    def angle_to(self, other) -> float:
        o = to_point(other)
        return math.degrees(math.atan2(o.y - self.y, o.x - self.x))

    def distance_to(self, other) -> float:
        o = to_point(other)
        return math.hypot(o.x - self.x, o.y - self.y)

    def lerp(self, other, t: float) -> "Point":
        o = to_point(other)
        return Point(self.x + (o.x - self.x) * t, self.y + (o.y - self.y) * t)

    def offset(self, dx: float = 0.0, dy: float = 0.0) -> "Point":
        return Point(self.x + dx, self.y + dy)

    # -- misc -----------------------------------------------------------
    @property
    def point(self) -> "Point":
        """Anchor protocol: a Point resolves to itself."""
        return self

    def __eq__(self, other) -> bool:
        if isinstance(other, Point):
            return self.x == other.x and self.y == other.y
        if isinstance(other, (tuple, list)) and len(other) == 2:
            return self.x == other[0] and self.y == other[1]
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.x, self.y))

    def __repr__(self) -> str:
        return f"Point({self.x:.4g}, {self.y:.4g})"


def to_point(obj) -> Point:
    """Coerce anything point-like into a :class:`Point`.

    Accepts ``Point``, ``(x, y)`` tuples/lists, anything exposing a ``.point``
    property (anchors, elements) or a ``.bbox`` (elements -> centre).
    """
    if isinstance(obj, Point):
        return obj
    if isinstance(obj, (tuple, list)) and len(obj) == 2:
        return Point(float(obj[0]), float(obj[1]))
    p = getattr(obj, "point", None)
    if p is not None:
        return p if isinstance(p, Point) else to_point(p)
    bb = getattr(obj, "bbox", None)
    if bb is not None:
        return bb.center
    raise TypeError(f"cannot interpret {obj!r} as a point")


@dataclass(frozen=True)
class BBox:
    """Axis-aligned bounding box, ``(x, y)`` = top-left corner."""

    x: float
    y: float
    w: float
    h: float

    # -- construction ---------------------------------------------------
    @staticmethod
    def from_corners(x0: float, y0: float, x1: float, y1: float) -> "BBox":
        return BBox(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))

    @staticmethod
    def from_points(points: Iterable) -> "BBox":
        pts = [to_point(p) for p in points]
        if not pts:
            return BBox(0.0, 0.0, 0.0, 0.0)
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        return BBox.from_corners(min(xs), min(ys), max(xs), max(ys))

    @staticmethod
    def union_all(boxes: Iterable["BBox"]) -> "BBox | None":
        out = None
        for b in boxes:
            if b is None:
                continue
            out = b if out is None else out.union(b)
        return out

    # -- edges / corners ------------------------------------------------
    @property
    def x0(self) -> float:
        return self.x

    @property
    def y0(self) -> float:
        return self.y

    @property
    def x1(self) -> float:
        return self.x + self.w

    @property
    def y1(self) -> float:
        return self.y + self.h

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    @property
    def center(self) -> Point:
        return Point(self.cx, self.cy)

    @property
    def size(self) -> Point:
        return Point(self.w, self.h)

    @property
    def corners(self) -> tuple:
        return (
            Point(self.x0, self.y0),
            Point(self.x1, self.y0),
            Point(self.x1, self.y1),
            Point(self.x0, self.y1),
        )

    # -- lookups --------------------------------------------------------
    def anchor(self, name: str) -> Point:
        key = str(name).lower().replace("_", "").replace("-", "")
        if key not in _ANCHOR_UV:
            raise KeyError(f"unknown anchor {name!r}; try one of {ANCHOR_NAMES}")
        u, v = _ANCHOR_UV[key]
        return Point(self.x + u * self.w, self.y + v * self.h)

    def uv(self, u: float, v: float) -> Point:
        """Point at fractional position ``(u, v)`` inside the box."""
        return Point(self.x + u * self.w, self.y + v * self.h)

    def at_angle(self, deg: float) -> Point:
        """Point on the box border along a ray from the centre.

        ``0`` points right (east), angles increase clockwise on screen.
        """
        a = deg2rad(deg)
        dx, dy = math.cos(a), math.sin(a)
        if self.w <= 0 or self.h <= 0:
            return self.center
        # Scale the ray so it lands exactly on the border of the rectangle.
        tx = float("inf") if dx == 0 else (self.w / 2.0) / abs(dx)
        ty = float("inf") if dy == 0 else (self.h / 2.0) / abs(dy)
        t = min(tx, ty)
        return Point(self.cx + dx * t, self.cy + dy * t)

    # -- combinators ----------------------------------------------------
    def union(self, other: "BBox") -> "BBox":
        return BBox.from_corners(
            min(self.x0, other.x0), min(self.y0, other.y0),
            max(self.x1, other.x1), max(self.y1, other.y1),
        )

    def intersection(self, other: "BBox") -> "BBox | None":
        x0 = max(self.x0, other.x0)
        y0 = max(self.y0, other.y0)
        x1 = min(self.x1, other.x1)
        y1 = min(self.y1, other.y1)
        if x1 <= x0 or y1 <= y0:
            return None
        return BBox.from_corners(x0, y0, x1, y1)

    def expand(self, pad=0.0, top=None, right=None, bottom=None, left=None) -> "BBox":
        """Grow the box outward. ``pad`` may be a scalar or a 2/4-tuple."""
        t, r, b, l = _expand_spec(pad)
        if top is not None:
            t = top
        if right is not None:
            r = right
        if bottom is not None:
            b = bottom
        if left is not None:
            l = left
        return BBox.from_corners(self.x0 - l, self.y0 - t, self.x1 + r, self.y1 + b)

    def shrink(self, pad=0.0, **kw) -> "BBox":
        t, r, b, l = _expand_spec(pad)
        return self.expand(0.0, top=-t, right=-r, bottom=-b, left=-l)

    def translated(self, dx: float, dy: float) -> "BBox":
        return BBox(self.x + dx, self.y + dy, self.w, self.h)

    def contains(self, p) -> bool:
        q = to_point(p)
        return self.x0 <= q.x <= self.x1 and self.y0 <= q.y <= self.y1

    def overlaps(self, other: "BBox") -> bool:
        return self.intersection(other) is not None

    def __eq__(self, other) -> bool:
        if isinstance(other, BBox):
            return (self.x, self.y, self.w, self.h) == \
                (other.x, other.y, other.w, other.h)
        if isinstance(other, (tuple, list)) and len(other) == 4:
            return (self.x, self.y, self.w, self.h) == tuple(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.x, self.y, self.w, self.h))

    def __repr__(self) -> str:
        return f"BBox(x={self.x:.4g}, y={self.y:.4g}, w={self.w:.4g}, h={self.h:.4g})"


def _expand_spec(pad) -> tuple:
    """Normalise a CSS-ish padding spec into ``(top, right, bottom, left)``."""
    if pad is None:
        return (0.0, 0.0, 0.0, 0.0)
    if isinstance(pad, (int, float)):
        return (float(pad),) * 4
    vals = list(pad)
    if len(vals) == 1:
        return (float(vals[0]),) * 4
    if len(vals) == 2:
        v, h = float(vals[0]), float(vals[1])
        return (v, h, v, h)
    if len(vals) == 3:
        t, h, b = map(float, vals)
        return (t, h, b, h)
    if len(vals) == 4:
        return tuple(map(float, vals))
    raise ValueError(f"bad padding spec: {pad!r}")


@dataclass(frozen=True)
class Affine:
    """2D affine transform ``[[a c e], [b d f]]`` matching the SVG matrix()."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    IDENTITY: "Affine" = None  # filled in below

    @staticmethod
    def translate(dx: float, dy: float = 0.0) -> "Affine":
        return Affine(1, 0, 0, 1, dx, dy)

    @staticmethod
    def scale(sx: float, sy: float = None) -> "Affine":
        sy = sx if sy is None else sy
        return Affine(sx, 0, 0, sy, 0, 0)

    @staticmethod
    def rotate(deg: float, about=(0.0, 0.0)) -> "Affine":
        o = to_point(about)
        r = deg2rad(deg)
        cs, sn = math.cos(r), math.sin(r)
        m = Affine(cs, sn, -sn, cs, 0, 0)
        return Affine.translate(o.x, o.y) @ m @ Affine.translate(-o.x, -o.y)

    @staticmethod
    def skew(deg_x: float = 0.0, deg_y: float = 0.0) -> "Affine":
        return Affine(1, math.tan(deg2rad(deg_y)), math.tan(deg2rad(deg_x)), 1, 0, 0)

    def __matmul__(self, other: "Affine") -> "Affine":
        """``self @ other`` applies *other* first, then *self*."""
        return Affine(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )

    def apply(self, p) -> Point:
        q = to_point(p)
        return Point(self.a * q.x + self.c * q.y + self.e,
                     self.b * q.x + self.d * q.y + self.f)

    def apply_bbox(self, bb: BBox) -> BBox:
        return BBox.from_points(self.apply(c) for c in bb.corners)

    @property
    def is_identity(self) -> bool:
        return (self.a, self.b, self.c, self.d, self.e, self.f) == (1, 0, 0, 1, 0, 0)

    def inverse(self) -> "Affine":
        det = self.a * self.d - self.b * self.c
        if abs(det) < 1e-12:
            raise ZeroDivisionError("affine transform is not invertible")
        ia, ib = self.d / det, -self.b / det
        ic, idd = -self.c / det, self.a / det
        ie = -(ia * self.e + ic * self.f)
        if_ = -(ib * self.e + idd * self.f)
        return Affine(ia, ib, ic, idd, ie, if_)

    def to_svg(self) -> str:
        n = _num
        return (f"matrix({n(self.a)},{n(self.b)},{n(self.c)},"
                f"{n(self.d)},{n(self.e)},{n(self.f)})")


Affine.IDENTITY = Affine()


def _num(v: float) -> str:
    """Compact float formatting for SVG output."""
    if v is None:
        return "0"
    if isinstance(v, str):
        return v
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def opposite_anchor(name: str) -> str:
    return _OPPOSITE.get(str(name).lower(), "center")


def anchor_normal(name: str) -> Point:
    nx, ny = _ANCHOR_NORMAL.get(str(name).lower(), (0.0, 0.0))
    return Point(nx, ny)


def polyline_length(pts: Sequence) -> float:
    pts = [to_point(p) for p in pts]
    return sum(pts[i].distance_to(pts[i + 1]) for i in range(len(pts) - 1))


def point_along(pts: Sequence, t: float) -> tuple:
    """Point (and unit direction) at fraction ``t`` along a polyline."""
    pts = [to_point(p) for p in pts]
    if len(pts) < 2:
        return (pts[0] if pts else Point(0, 0)), Point(1, 0)
    total = polyline_length(pts)
    if total == 0:
        return pts[0], Point(1, 0)
    target = max(0.0, min(1.0, t)) * total
    acc = 0.0
    for i in range(len(pts) - 1):
        seg = pts[i].distance_to(pts[i + 1])
        if acc + seg >= target or i == len(pts) - 2:
            local = 0.0 if seg == 0 else (target - acc) / seg
            local = max(0.0, min(1.0, local))
            return pts[i].lerp(pts[i + 1], local), (pts[i + 1] - pts[i]).normalized()
        acc += seg
    return pts[-1], (pts[-1] - pts[-2]).normalized()
