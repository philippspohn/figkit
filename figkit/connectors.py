"""Arrows and connectors: straight, elbow, curved, or via waypoints.

Endpoints are stored as *live references* — anchors, elements or raw points —
and resolved at render time, so moving a box drags its arrows along.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .core import Anchor, Element
from .geom import BBox, Point, polyline_length, to_point
from .paint import paint_attrs
from .svgdoc import Node, RenderContext
from .svgpath import (fmt, flatten_path, path_bbox, path_from_points,
                      path_length, point_at, rounded_polyline)
from .text import Text

__all__ = [
    "Connector", "arrow", "line", "elbow", "curve", "connect", "double_arrow",
    "self_loop", "PathAnchor", "Handle", "HEADS",
]

HEADS = ("triangle", "stealth", "open", "vee", "circle", "dot", "diamond",
         "square", "bar", "tee", "cross", "none")

_SIDE_NORMAL = {"n": Point(0, -1), "s": Point(0, 1),
                "e": Point(1, 0), "w": Point(-1, 0)}


@dataclass(frozen=True)
class Handle:
    """One end's Bezier handle — the "whisker" a vector editor lets you drag.

    ``angle`` turns the handle off the direction the curve would leave in
    anyway (the face you attached to, or the chord for a bare point), and
    ``length`` says how far it reaches as a fraction of the straight-line
    distance between the endpoints. A fraction rather than a distance so the
    curve keeps its shape when the things it connects move apart::

        curve(a.e, b.w, start_handle=0.6, end_handle=(0.2, -30))

    Pass ``px`` for an absolute reach in figure units instead; it does not
    follow the layout, so prefer ``length`` unless you need an exact number.

    ``start_handle=`` and ``end_handle=`` also take the shorthands a bare
    number (``0.6``) and a tuple of this class's arguments (``(0.2, -30)``).
    """

    length: float = 0.4
    angle: float = 0.0
    px: float = None

    def direction(self, base: Point) -> Point:
        """``base`` turned by ``angle`` degrees (clockwise on screen)."""
        if not self.angle:
            return base.normalized()
        a = math.radians(self.angle)
        c, s = math.cos(a), math.sin(a)
        u = base.normalized()
        return Point(u.x * c - u.y * s, u.x * s + u.y * c)

    def reach(self, chord: float) -> float:
        """How far the handle extends, given the endpoint separation."""
        return float(self.px) if self.px is not None else self.length * chord


def _as_handle(spec) -> Handle | None:
    """Accept a ``Handle``, a bare fraction, or a tuple of its arguments."""
    if spec is None or isinstance(spec, Handle):
        return spec
    if isinstance(spec, (int, float)):
        return Handle(float(spec))
    try:
        args = tuple(spec)
    except TypeError:
        args = ()
    if 1 <= len(args) <= 3:
        return Handle(*args)
    raise ValueError(f"cannot read {spec!r} as a handle; pass a number, a "
                     f"tuple of Handle arguments, or a Handle")


class PathAnchor(Anchor):
    """A live anchor at a fraction ``t`` along a connector's path.

    Unlike a bare point it re-resolves on read, so anything attached to the
    middle of an arrow follows the arrow when its endpoints move.
    """

    __slots__ = ("t",)

    def __init__(self, connector, t: float = 0.5, dx: float = 0.0,
                 dy: float = 0.0):
        super().__init__(connector, name=None, dx=dx, dy=dy)
        self.t = float(t)

    @property
    def point(self) -> Point:
        p = self.element.point_at(self.t)
        return Point(p.x + self.dx, p.y + self.dy)

    @property
    def normal(self) -> Point:
        d = self.element.direction_at(self.t)
        return Point(-d.y, d.x)

    def offset(self, dx: float = 0.0, dy: float = 0.0) -> "PathAnchor":
        return PathAnchor(self.element, self.t, self.dx + dx, self.dy + dy)

    def __repr__(self) -> str:
        return f"<PathAnchor t={self.t:g} -> {self.point}>"


# ==========================================================================
# Arrow heads
# ==========================================================================

def _head_geometry(kind: str, tip: Point, direction: Point, size: float,
                   width_ratio: float = 0.62) -> tuple:
    """Return ``(path_or_None, node_kwargs, inset)`` for one arrow head.

    ``inset`` is how far back along the line the stroke should stop so it does
    not poke out of the head.
    """
    kind = (kind or "none").lower()
    if kind in ("none", "", "off"):
        return None, {}, 0.0
    d = direction.normalized()
    if d.length == 0:
        d = Point(1, 0)
    n = Point(-d.y, d.x)          # perpendicular
    half = size * width_ratio

    if kind in ("triangle", "arrow", "filled"):
        back = tip - d * size
        pts = [tip, back + n * half, back - n * half]
        return path_from_points(pts, close=True), {"filled": True}, size * 0.92
    if kind == "stealth":
        back = tip - d * size
        notch = tip - d * (size * 0.55)
        pts = [tip, back + n * half, notch, back - n * half]
        return path_from_points(pts, close=True), {"filled": True}, size * 0.6
    if kind in ("open", "vee", "v", "line"):
        back = tip - d * size
        d_path = (f"M{fmt((back + n * half).x)} {fmt((back + n * half).y)}"
                  f"L{fmt(tip.x)} {fmt(tip.y)}"
                  f"L{fmt((back - n * half).x)} {fmt((back - n * half).y)}")
        return d_path, {"filled": False}, size * 0.35
    if kind in ("circle", "dot", "disc"):
        r = size * 0.42
        c = tip - d * r
        return None, {"circle": (c, r), "filled": kind != "circle_open"}, r * 1.9
    if kind == "diamond":
        c = tip - d * (size / 2.0)
        pts = [tip, c + n * half, tip - d * size, c - n * half]
        return path_from_points(pts, close=True), {"filled": True}, size * 0.95
    if kind in ("square", "box"):
        c = tip - d * (size * 0.4)
        h = size * 0.4
        pts = [c + d * h + n * h, c + d * h - n * h,
               c - d * h - n * h, c - d * h + n * h]
        return path_from_points(pts, close=True), {"filled": True}, size * 0.78
    if kind in ("bar", "tee", "stop"):
        d_path = (f"M{fmt((tip + n * half).x)} {fmt((tip + n * half).y)}"
                  f"L{fmt((tip - n * half).x)} {fmt((tip - n * half).y)}")
        return d_path, {"filled": False}, 0.0
    if kind == "cross":
        h = size * 0.45
        d_path = (f"M{fmt((tip + n * h + d * h).x)} {fmt((tip + n * h + d * h).y)}"
                  f"L{fmt((tip - n * h - d * h).x)} {fmt((tip - n * h - d * h).y)}"
                  f"M{fmt((tip - n * h + d * h).x)} {fmt((tip - n * h + d * h).y)}"
                  f"L{fmt((tip + n * h - d * h).x)} {fmt((tip + n * h - d * h).y)}")
        return d_path, {"filled": False}, 0.0
    raise ValueError(f"unknown arrow head {kind!r}; use one of {HEADS}")


# ==========================================================================
# Connector
# ==========================================================================

class Connector(Element):
    """A line between two live endpoints, with optional heads and a label.

    Prefer the helpers :func:`arrow`, :func:`elbow`, :func:`curve` and
    :func:`line` — they are the same class with different defaults.
    """

    role = "arrow"
    STROKE_WIDTH_ALIAS = True

    def __init__(self, start, end, *, route: str = "straight", waypoints=None,
                 stub: float = 14.0, bend: float = 0.0, bow: float = 0.0,
                 corner: float = 6.0, tension: float = 0.5,
                 start_handle=None, end_handle=None,
                 gap: float = 0.0, start_gap: float = None, end_gap: float = None,
                 head=None, tail=None, head_size=None, tail_size=None,
                 start_side: str = None, end_side: str = None,
                 label=None, label_pos: float = 0.5, label_offset: float = 9.0,
                 label_side: str = "auto", label_style=None, label_bg=None,
                 label_rotate: bool = False, **kw):
        self.start_ref = start
        self.end_ref = end
        self.route = str(route).lower()
        self.waypoints = list(waypoints or [])
        self.stub = float(stub)
        self.bend = float(bend)
        self.bow = float(bow)
        self.corner = float(corner)
        self.tension = float(tension)
        self.start_handle = _as_handle(start_handle)
        self.end_handle = _as_handle(end_handle)
        self.start_gap = float(gap if start_gap is None else start_gap)
        self.end_gap = float(gap if end_gap is None else end_gap)
        self.start_side = start_side
        self.end_side = end_side
        self._head = head
        self._tail = tail
        self._head_size = head_size
        self._tail_size = tail_size
        self.label_pos = float(label_pos)
        self.label_offset = float(label_offset)
        self.label_side = label_side
        self.label_bg = label_bg
        self.label_rotate = label_rotate
        self._label: Text | None = None
        super().__init__(0, 0, None, None, **kw)
        if label is not None and label != "":
            self._label = Text(label, add=False, style=label_style)
            self._label.parent = self
            self._label.role = "label"

    # -- endpoint resolution ---------------------------------------------
    def _endpoint(self, ref, toward: Point, side: str = None) -> tuple:
        """Resolve one endpoint to ``(point, outward_normal)``."""
        if isinstance(ref, Anchor):
            p = ref.point
            n = ref.normal
            if n.length == 0:
                n = (p - toward).normalized()
            return p, n
        if isinstance(ref, Element):
            bb = ref.bbox
            if side:
                key = str(side).lower()[:2]
                key = {"to": "n", "bo": "s", "le": "w", "ri": "e"}.get(key, key[0])
                p = bb.anchor(key)
                return p, _SIDE_NORMAL.get(key, Point(0, 0))
            angle = math.degrees(math.atan2(toward.y - bb.cy, toward.x - bb.cx))
            p = bb.at_angle(angle)
            n = _dominant_normal(p, bb)
            return p, n
        p = to_point(ref)
        return p, Point(0, 0)

    def endpoints(self) -> tuple:
        """``((p0, n0), (p1, n1))`` resolved right now."""
        hint_a = to_point(self.waypoints[0]) if self.waypoints else _rough(self.end_ref)
        hint_b = to_point(self.waypoints[-1]) if self.waypoints else _rough(self.start_ref)
        a = self._endpoint(self.start_ref, hint_a, self.start_side)
        b = self._endpoint(self.end_ref, hint_b, self.end_side)
        if not self.waypoints:
            a = self._endpoint(self.start_ref, b[0], self.start_side)
            b = self._endpoint(self.end_ref, a[0], self.end_side)
        return a, b

    # -- geometry --------------------------------------------------------
    def geometry(self) -> tuple:
        """``(path_data, start_point, start_dir, end_point, end_dir)``."""
        (p0, n0), (p1, n1) = self.endpoints()
        if self.start_gap:
            p0 = p0 + (n0 if n0.length else (p1 - p0).normalized()) * self.start_gap
        if self.end_gap:
            p1 = p1 + (n1 if n1.length else (p0 - p1).normalized()) * self.end_gap
        wp = [to_point(w) for w in self.waypoints]
        route = self.route

        if route in ("elbow", "orth", "orthogonal", "hv", "vh", "manhattan"):
            pts = _elbow_points(p0, n0, p1, n1, self.stub, route, wp)
            d = rounded_polyline(pts, self.corner) if self.corner else \
                path_from_points(pts)
            sd = (pts[1] - pts[0]) if len(pts) > 1 else Point(1, 0)
            ed = (pts[-1] - pts[-2]) if len(pts) > 1 else Point(1, 0)
            return d, p0, sd, p1, ed

        if route in ("curve", "bezier", "spline", "arc"):
            d, sd, ed = _curve_path(p0, n0, p1, n1, wp, self.bend, self.bow,
                                    arc=(route == "arc"),
                                    h0=self.start_handle, h1=self.end_handle,
                                    tension=self.tension)
            return d, p0, sd, p1, ed

        pts = [p0] + wp + [p1]
        if self.corner and wp:
            d = rounded_polyline(pts, self.corner)
        else:
            d = path_from_points(pts)
        sd = (pts[1] - pts[0]) if len(pts) > 1 else Point(1, 0)
        ed = (pts[-1] - pts[-2]) if len(pts) > 1 else Point(1, 0)
        return d, p0, sd, p1, ed

    def path_data(self, bb: BBox = None) -> str:
        return self.geometry()[0]

    def polyline(self, steps: int = 24) -> list:
        pts: list = []
        for poly in flatten_path(self.path_data(), steps):
            pts.extend(poly)
        return [Point(*p) for p in pts]

    def point_at(self, t: float) -> Point:
        """Point at fraction ``t`` (0..1) along the connector."""
        return point_at(self.path_data(), t)[0]

    def direction_at(self, t: float) -> Point:
        return point_at(self.path_data(), t)[1]

    def anchor_at(self, t: float) -> PathAnchor:
        """A *live* anchor at fraction ``t`` along the path."""
        return PathAnchor(self, t)

    @property
    def mid(self) -> PathAnchor:
        """A live anchor at the midpoint of the path."""
        return PathAnchor(self, 0.5)

    @property
    def length(self) -> float:
        return polyline_length(self.polyline())

    def _measure(self) -> None:
        d = self.path_data()
        x0, y0, x1, y1 = path_bbox(d) if d else (0, 0, 0, 0)
        self._x, self._y = x0, y0
        self._w, self._h = x1 - x0, y1 - y0
        if self._label is not None:
            self._place_label()

    @property
    def local_bbox(self) -> BBox:
        self._dirty = True          # endpoints are live; always re-measure
        self._ensure()
        bb = BBox(self._x, self._y, self._w or 0.0, self._h or 0.0)
        if self._label is not None:
            bb = bb.union(self._label.local_bbox)
        return bb

    # -- label -----------------------------------------------------------
    @property
    def label(self) -> Text | None:
        self._ensure()
        return self._label

    def set_label(self, text, **style) -> "Connector":
        if self._label is None:
            self._label = Text(text, add=False)
            self._label.parent = self
            self._label.role = "label"
        else:
            self._label.text = text
        if style:
            self._label.restyle(**style)
        return self.invalidate()

    def _place_label(self) -> None:
        self._label.reset_transform()      # placement re-runs on every measure
        p, d = point_at(self.path_data(), self.label_pos)
        n = Point(-d.y, d.x)
        side = str(self.label_side).lower()
        if side in ("auto", "above", "left"):
            if n.y > 0:
                n = -n
        elif side in ("below", "right"):
            if n.y < 0:
                n = -n
        elif side in ("none", "on", "center"):
            n = Point(0, 0)
        target = p + n * self.label_offset
        anchor = "center"
        if self.label_rotate:
            anchor = "center"      # a rotated label reads best centred
        elif abs(n.x) > abs(n.y) and n.length:
            anchor = "w" if n.x > 0 else "e"
        elif n.length:
            anchor = "n" if n.y > 0 else "s"
        self._label.at(target.x, target.y, anchor=anchor)
        if self.label_rotate:
            angle = math.degrees(math.atan2(d.y, d.x))
            if angle > 90 or angle < -90:      # keep the text right way up
                angle += 180
            self._label.rotate(angle)

    # -- rendering -------------------------------------------------------
    def _render_content(self, ctx: RenderContext):
        d, p0, sd, p1, ed = self.geometry()
        if not d:
            return None
        stroke = self.prop("stroke", None)
        stroke_w = self.prop("stroke_width", 1.5) or 1.5
        head_kind = self._head if self._head is not None else self.prop("head")
        tail_kind = self._tail if self._tail is not None else self.prop("tail")
        head_size = float(self._head_size if self._head_size is not None
                          else self.prop("head_size", 9))
        tail_size = float(self._tail_size if self._tail_size is not None
                          else self.prop("tail_size", head_size))
        # heads scale a little with the line weight so they never look pinned on
        head_size = head_size * (0.72 + 0.28 * max(1.0, float(stroke_w)))
        tail_size = tail_size * (0.72 + 0.28 * max(1.0, float(stroke_w)))

        nodes: list = []
        head_nodes: list = []
        has_head = bool(head_kind) and str(head_kind).lower() != "none"
        has_tail = bool(tail_kind) and str(tail_kind).lower() != "none"

        # How far back the stroke has to stop for each head to cover its end.
        trim_end = _head_inset(head_kind, head_size) if has_head else 0.0
        trim_start = _head_inset(tail_kind, tail_size) if has_tail else 0.0
        shrink = _head_budget(trim_start + trim_end, path_length(d))
        if shrink < 1.0:
            # The heads wanted more room than the connector has. Left alone
            # they eat the whole shaft and overshoot its ends, which reads as
            # a stray triangle rather than an arrow.
            if shrink < 0.5:
                ctx.warn(f"connector is {path_length(d):.0f}pt long but its "
                         f"heads need {trim_start + trim_end:.0f}pt; shrinking "
                         f"them to fit (set head_size= to choose)")
            head_size *= shrink
            tail_size *= shrink
            trim_end = _head_inset(head_kind, head_size) if has_head else 0.0
            trim_start = _head_inset(tail_kind, tail_size) if has_tail else 0.0
        if trim_start or trim_end:
            d = _trim_path(d, trim_start, trim_end)

        # Point each head from where the stroke now ends toward the tip, rather
        # than along the tangent at the tip. On a curve those differ, and using
        # the tangent lets the stroke escape sideways from under the head.
        if has_head:
            ed = _aim(d, p1, ed, at_start=False)
            hd, meta, _ = _head_geometry(head_kind, p1, ed, head_size)
            head_nodes.append(_head_node(hd, meta, stroke, stroke_w, self, ctx))
        if has_tail:
            sd = -_aim(d, p0, -sd, at_start=True)
            td, meta, _ = _head_geometry(tail_kind, p0, -sd, tail_size)
            head_nodes.append(_head_node(td, meta, stroke, stroke_w, self, ctx))

        line_attrs = paint_attrs(self, ctx)
        line_attrs["fill"] = "none"
        nodes.append(Node("path", d=d, **line_attrs))
        nodes.extend(n for n in head_nodes if n is not None)

        if self._label is not None:
            self._ensure()
            if self.label_bg:
                lb = self._label.local_bbox.expand((2, 4))
                bg = self.label_bg if isinstance(self.label_bg, str) else "#ffffff"
                nodes.append(Node("rect", x=lb.x, y=lb.y, width=lb.w,
                                  height=lb.h, rx=3, fill=bg, stroke="none"))
            n = self._label.render(ctx)
            if n is not None:
                nodes.append(n)
        return nodes


#: Most of a short connector should still be line rather than arrow head.
_MAX_HEAD_SHARE = 0.6


def _head_budget(inset: float, length: float) -> float:
    """How much the heads must shrink by to leave a visible shaft."""
    if inset <= 0 or length <= 0:
        return 1.0
    return min(1.0, _MAX_HEAD_SHARE * length / inset)


def _head_inset(kind: str, size: float) -> float:
    """How far short of the tip the stroke must stop for this head shape."""
    _d, _meta, inset = _head_geometry(kind, Point(0, 0), Point(1, 0), size)
    return inset


def _aim(d: str, tip: Point, fallback: Point, at_start: bool) -> Point:
    """Direction from the (already trimmed) stroke end toward ``tip``."""
    if not d:
        return fallback
    polys = flatten_path(d, 8)
    if not polys or not polys[0]:
        return fallback
    end = Point(*(polys[0][0] if at_start else polys[-1][-1]))
    direction = tip - end
    return direction.normalized() if direction.length > 1e-6 else fallback


def _head_node(d, meta, stroke, stroke_w, el, ctx) -> Node | None:
    color = stroke if stroke not in (None, "none") else el.prop("fill", "#000")
    if "circle" in meta:
        c, r = meta["circle"]
        return Node("ellipse", cx=c.x, cy=c.y, rx=r, ry=r, fill=color,
                    stroke="none")
    if d is None:
        return None
    if meta.get("filled"):
        return Node("path", d=d, fill=color, stroke="none")
    return Node("path", d=d, fill="none", stroke=color, stroke_width=stroke_w,
                stroke_linecap="round", stroke_linejoin="round")


def _rough(ref) -> Point:
    """A cheap point for an endpoint, used only to orient the other end."""
    if isinstance(ref, Anchor):
        return ref.point
    if isinstance(ref, Element):
        return ref.bbox.center
    return to_point(ref)


def _dominant_normal(p: Point, bb: BBox) -> Point:
    """Which side of ``bb`` does point ``p`` sit on?"""
    tol = 1e-6
    if abs(p.x - bb.x0) < tol:
        return Point(-1, 0)
    if abs(p.x - bb.x1) < tol:
        return Point(1, 0)
    if abs(p.y - bb.y0) < tol:
        return Point(0, -1)
    if abs(p.y - bb.y1) < tol:
        return Point(0, 1)
    return Point(0, 0)


def _elbow_points(p0: Point, n0: Point, p1: Point, n1: Point, stub: float,
                  mode: str, waypoints: list) -> list:
    """Orthogonal route from ``p0`` to ``p1`` honouring the exit normals."""
    if waypoints:
        pts = [p0]
        prev = p0
        for w in waypoints:
            pts.extend(_ortho_pair(prev, w))
            prev = w
        pts.extend(_ortho_pair(prev, p1))
        pts.append(p1)
        return _dedupe(pts)

    if n0.length == 0 and n1.length == 0:
        n0, n1 = _infer_normals(p0, p1, mode)
    elif n0.length == 0:
        n0 = -n1 if abs(n1.x) > abs(n1.y) else -n1
    elif n1.length == 0:
        n1 = -n0

    a = p0 + n0 * stub
    b = p1 + n1 * stub
    h0 = abs(n0.x) > abs(n0.y)
    h1 = abs(n1.x) > abs(n1.y)

    if h0 and h1:
        mx = (a.x + b.x) / 2.0
        pts = [p0, a, Point(mx, a.y), Point(mx, b.y), b, p1]
    elif (not h0) and (not h1):
        my = (a.y + b.y) / 2.0
        pts = [p0, a, Point(a.x, my), Point(b.x, my), b, p1]
    elif h0 and not h1:
        pts = [p0, a, Point(b.x, a.y), b, p1]
    else:
        pts = [p0, a, Point(a.x, b.y), b, p1]
    return _dedupe(pts)


def _ortho_pair(a: Point, b: Point) -> list:
    b = to_point(b)
    if abs(b.x - a.x) < 1e-9 or abs(b.y - a.y) < 1e-9:
        return []
    return [Point(b.x, a.y)]


def _infer_normals(p0: Point, p1: Point, mode: str) -> tuple:
    dx, dy = p1.x - p0.x, p1.y - p0.y
    horizontal_first = abs(dx) >= abs(dy)
    if mode == "hv":
        horizontal_first = True
    elif mode == "vh":
        horizontal_first = False
    if horizontal_first:
        n0 = Point(1 if dx >= 0 else -1, 0)
        n1 = Point(0, -1 if dy >= 0 else 1)
    else:
        n0 = Point(0, 1 if dy >= 0 else -1)
        n1 = Point(-1 if dx >= 0 else 1, 0)
    return n0, n1


def _dedupe(pts: list) -> list:
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p.x - out[-1].x) > 1e-7 or abs(p.y - out[-1].y) > 1e-7:
            out.append(p)
    return out


def _curve_path(p0: Point, n0: Point, p1: Point, n1: Point, waypoints: list,
                bend: float, bow: float = 0.0, arc: bool = False,
                h0: Handle = None, h1: Handle = None,
                tension: float = 0.5) -> tuple:
    """Build the curve.

    ``bend`` deepens the bow: when the endpoints are anchors (so we know which
    way they face) it lengthens the handles *along those normals*; for plain
    points there is no normal to follow, so it bows sideways instead.
    ``bow`` always displaces sideways, positive = left of travel.

    ``h0`` and ``h1`` place an end's control point outright. An end given a
    handle ignores ``bend`` and ``bow``, which exist to guess at what the
    handle says explicitly.
    """
    chord = p1 - p0
    dist = chord.length or 1.0
    u = chord.normalized()
    base0 = n0 if n0.length else u
    base1 = n1 if n1.length else -u

    if waypoints:
        pts = [p0] + waypoints + [p1]
        # Pin the outer tangents to the faces the curve is attached to, so
        # adding a waypoint does not swing the arrow off the box it leaves.
        start = _spline_tangent(h0, base0, dist, pts[0], pts[1], tension)
        end = _spline_tangent(h1, base1, dist, pts[-1], pts[-2], tension)
        d = _catmull_rom(pts, tension, start_c=start, end_c=end)
        return d, (start - p0), (p1 - end)

    left = Point(chord.y, -chord.x).normalized()   # left of travel (y is down)

    if arc or (n0.length == 0 and n1.length == 0 and h0 is None and h1 is None):
        b = bend + bow if (bend or bow) else 0.25
        mid = p0.lerp(p1, 0.5) + left * (dist * b)
        d = (f"M{fmt(p0.x)} {fmt(p0.y)}Q{fmt(mid.x)} {fmt(mid.y)} "
             f"{fmt(p1.x)} {fmt(p1.y)}")
        return d, (mid - p0), (p1 - mid)

    reach = max(0.18, abs(bend))
    push = left * (dist * bow * 0.6)
    c0 = _control_point(p0, base0, h0, u, dist, reach, push)
    c1 = _control_point(p1, base1, h1, -u, dist, reach, push)
    d = (f"M{fmt(p0.x)} {fmt(p0.y)}C{fmt(c0.x)} {fmt(c0.y)} "
         f"{fmt(c1.x)} {fmt(c1.y)} {fmt(p1.x)} {fmt(p1.y)}")
    return d, (c0 - p0), (p1 - c1)


def _control_point(p: Point, base: Point, h: Handle, along: Point,
                   dist: float, reach: float, push: Point) -> Point:
    """Where one end's Bezier control point lands.

    Without a handle the reach follows how well the exit direction lines up
    with the chord, so a sideways exit gets a short handle and the curve stays
    tidy; ``bend`` raises the floor on that and ``bow`` displaces it sideways.
    """
    if h is not None:
        return p + h.direction(base) * h.reach(dist)
    k = min(dist * 0.9, max(10.0, dist * 0.55 * max(abs(along.dot(base)), reach)))
    return p + base * k + push


def _spline_tangent(h: Handle, base: Point, dist: float, end: Point,
                    neighbour: Point, tension: float) -> Point:
    """The control point next to a spline's first or last knot.

    Without a handle the reach is the one Catmull-Rom would have chosen, so
    pinning the direction changes where the curve leaves, not how far it
    swings before it gets going.
    """
    if h is not None:
        return end + h.direction(base) * h.reach(dist)
    return end + base.normalized() * ((neighbour - end).length * tension / 3.0)


def _catmull_rom(points: list, tension: float = 0.5, start_c: Point = None,
                 end_c: Point = None) -> str:
    """Smooth cubic spline through all the points.

    ``start_c`` and ``end_c`` override the control points adjacent to the
    first and last knot, which is how an attached curve keeps its facing.
    """
    pts = [to_point(p) for p in points]
    if len(pts) < 3:
        return path_from_points(pts)
    ext = [pts[0]] + pts + [pts[-1]]
    segments = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        segments.append([p1 + (p2 - p0) * (tension / 3.0),
                         p2 - (p3 - p1) * (tension / 3.0), p2])
    if start_c is not None:
        segments[0][0] = start_c
    if end_c is not None:
        segments[-1][1] = end_c
    parts = [f"M{fmt(pts[0].x)} {fmt(pts[0].y)}"]
    for c1, c2, p2 in segments:
        parts.append(f"C{fmt(c1.x)} {fmt(c1.y)} {fmt(c2.x)} {fmt(c2.y)} "
                     f"{fmt(p2.x)} {fmt(p2.y)}")
    return "".join(parts)


def _trim_path(d: str, start: float, end: float) -> str:
    """Shorten a path from both ends so arrow heads sit flush."""
    polys = flatten_path(d, 28)
    if not polys:
        return d
    pts = [Point(*p) for p in polys[0]]
    for poly in polys[1:]:
        pts.extend(Point(*p) for p in poly)
    if len(pts) < 2:
        return d
    total = polyline_length(pts)
    if total <= start + end + 0.5:
        return ""
    if start > 0:
        pts = _cut(pts, start, from_start=True)
    if end > 0:
        pts = _cut(pts, end, from_start=False)
    return path_from_points(pts)


def _cut(pts: list, amount: float, from_start: bool) -> list:
    work = list(pts) if from_start else list(reversed(pts))
    acc = 0.0
    for i in range(len(work) - 1):
        seg = work[i].distance_to(work[i + 1])
        if acc + seg >= amount:
            t = (amount - acc) / seg if seg else 0.0
            new_pt = work[i].lerp(work[i + 1], t)
            out = [new_pt] + work[i + 1:]
            return out if from_start else list(reversed(out))
        acc += seg
    return pts


# ==========================================================================
# Friendly constructors
# ==========================================================================

def arrow(start, end, **kw) -> Connector:
    """A straight arrow from ``start`` to ``end``.

    >>> arrow(fe.e, fm.w)
    >>> arrow(box_a, box_b, head="stealth", label="loss")
    """
    kw.setdefault("route", "straight")
    return Connector(start, end, **kw)


def line(start, end, **kw) -> Connector:
    """A plain line (no arrow head)."""
    kw.setdefault("route", "straight")
    kw.setdefault("head", "none")
    return Connector(start, end, **kw)


def elbow(start, end, stub: float = 14.0, **kw) -> Connector:
    """An orthogonal ``-|`` style connector with a straight ``stub`` at each end."""
    kw.setdefault("route", "elbow")
    return Connector(start, end, stub=stub, **kw)


def curve(start, end, bend: float = 0.0, **kw) -> Connector:
    """A smooth curve between two endpoints.

    ``bend`` deepens the bow — following the anchors' facing direction when
    you connect anchors (``a.s`` leaves downward), or sideways for plain
    points.  ``bow=`` always pushes sideways (positive = left of travel), and
    ``waypoints=[...]`` routes the curve through specific points.

    For control over the shape rather than a nudge to it, place either end's
    Bezier handle with ``start_handle=`` / ``end_handle=`` (see :class:`Handle`)::

        curve(a.e, b.w, start_handle=0.8, end_handle=0.15)
    """
    kw.setdefault("route", "curve")
    return Connector(start, end, bend=bend, **kw)


def connect(start, end, route: str = "straight", **kw) -> Connector:
    """Generic entry point: ``route`` is straight / elbow / curve / arc."""
    return Connector(start, end, route=route, **kw)


def double_arrow(start, end, **kw) -> Connector:
    """An arrow with heads on both ends."""
    kw.setdefault("tail", kw.get("head", "triangle"))
    return Connector(start, end, **kw)


def self_loop(element, side: str = "top", size: float = 36.0,
              spread: float = 0.45, **kw) -> Connector:
    """An arrow that leaves one element and comes back to it.

    The staple of state machines and recurrent blocks. ``side`` picks the edge
    it bulges from, ``size`` how far out it goes and ``spread`` how far apart
    its feet sit, as a fraction of that edge.

    >>> self_loop(state, side="top", label="retry")
    """
    box = element.bbox
    half = max(0.02, min(0.9, float(spread))) / 2.0
    s = str(side).lower()
    if s in ("top", "n", "up"):
        start, end = box.uv(0.5 - half, 0.0), box.uv(0.5 + half, 0.0)
        apex = Point(box.cx, box.y0 - size)
    elif s in ("bottom", "s", "down"):
        start, end = box.uv(0.5 + half, 1.0), box.uv(0.5 - half, 1.0)
        apex = Point(box.cx, box.y1 + size)
    elif s in ("left", "w"):
        start, end = box.uv(0.0, 0.5 + half), box.uv(0.0, 0.5 - half)
        apex = Point(box.x0 - size, box.cy)
    elif s in ("right", "e"):
        start, end = box.uv(1.0, 0.5 - half), box.uv(1.0, 0.5 + half)
        apex = Point(box.x1 + size, box.cy)
    else:
        raise ValueError(f"side={side!r}; use top/bottom/left/right")
    kw.setdefault("route", "curve")
    # Put any label outside the loop rather than inside its arc.
    kw.setdefault("label_side", {"bottom": "below", "s": "below",
                                 "down": "below"}.get(s, "above"))
    return Connector(start, end, waypoints=[apex], **kw)
