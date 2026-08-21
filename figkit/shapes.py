"""Drawable shapes: boxes, ellipses, polygons, paths and friends."""

from __future__ import annotations

import math

from .core import Element
from .geom import Affine, BBox, Point, _expand_spec, to_point
from .paint import paint_attrs
from .svgdoc import Node, RenderContext
from .text import Text
from .svgpath import (fmt, path_bbox, path_from_points, rounded_polyline,
                      transform_path_data)

__all__ = [
    "Shape", "Box", "Rect", "Pill", "Ellipse", "Circle", "Diamond", "Triangle",
    "Hexagon", "Parallelogram", "Cylinder", "Note", "Chevron", "Stadium",
    "Path", "Polygon", "Polyline", "Line", "Dot", "Marker", "Star",
]


# ==========================================================================
# Base class for label-carrying shapes
# ==========================================================================

class Shape(Element):
    """A filled/stroked shape that can auto-size around a text label.

    Subclasses override :meth:`shape_nodes` to draw themselves.
    """

    role = "box"
    default_padding = (8, 12)

    def __init__(self, text=None, x: float = 0.0, y: float = 0.0,
                 w: float = None, h: float = None, *, padding=None,
                 min_w: float = 0.0, min_h: float = 0.0,
                 max_w: float = None, wrap=None, content: Element = None,
                 label_style=None, markup: bool = False, aspect: float = None,
                 **kw):
        self._label: Text | None = None
        self._content: Element | None = None
        self.min_w = float(min_w or 0)
        self.min_h = float(min_h or 0)
        self.max_w = max_w
        self.aspect = aspect
        self._wrap = wrap
        self._label_style = label_style
        self._markup = markup
        if padding is not None:
            kw["padding"] = padding
        super().__init__(x, y, w, h, **kw)
        if text is not None and text != "":
            self._label = Text(text, markup=markup, add=False,
                               style=label_style)
            self._label.parent = self
            self._label.role = "text"
        if content is not None:
            self.set_content(content)
        self.invalidate()

    # -- content ---------------------------------------------------------
    @property
    def label(self) -> Text | None:
        """The inner :class:`~figkit.text.Text` element (or ``None``)."""
        self._ensure()
        return self._label

    @property
    def text(self) -> str:
        return self._label.text if self._label else ""

    @text.setter
    def text(self, value) -> None:
        if self._label is None:
            self._label = Text(value, markup=self._markup, add=False,
                               style=self._label_style)
            self._label.parent = self
        else:
            self._label.text = value
        self.invalidate()

    def set_text(self, value, **style) -> "Shape":
        self.text = value
        if style and self._label is not None:
            self._label.restyle(**style)
        return self

    def set_content(self, element: Element) -> "Shape":
        """Put an arbitrary element inside; the box sizes around it."""
        if element.parent is not None:
            element.parent.remove_child(element)
        self._content = element
        element.parent = self
        return self.invalidate()

    @property
    def content(self) -> Element | None:
        return self._content

    def padding(self) -> tuple:
        pad = self.prop("padding", None)
        if pad is None:
            pad = self.default_padding
        return _expand_spec(pad)

    # -- measurement -----------------------------------------------------
    def _inner_size(self) -> tuple:
        top, right, bottom, left = self.padding()
        # wrap: None -> wrap to the inner width when the width is pinned;
        #       True -> same; False -> never wrap; a number -> wrap at it.
        wrap = self._wrap
        inner_w = max(1.0, float(self._w or 0) - left - right)
        # Padding can exceed a small shape (a Circle with generous padding, say).
        # Wrapping to a sliver would collapse the label to zero width, so only
        # wrap when there is a usable amount of room.
        usable = inner_w if inner_w > 8 else None
        if wrap is False:
            wrap = None
        elif wrap is True or wrap is None:
            wrap = usable if self._explicit_w else None
        if self._label is not None:
            self._label._wrap = wrap if wrap else None
            self._label.invalidate()
            lb = self._label.local_bbox
            cw, ch = lb.w, lb.h
        else:
            cw = ch = 0.0
        if self._content is not None:
            cb = self._content.bbox
            cw = max(cw, cb.w)
            ch = max(ch, cb.h) if self._label is None else ch + cb.h
        return cw, ch

    def _measure(self) -> None:
        top, right, bottom, left = self.padding()
        cw, ch = self._inner_size()
        if not self._explicit_w:
            self._w = max(self.min_w, cw + left + right)
            if self.max_w:
                self._w = min(self._w, float(self.max_w))
        if not self._explicit_h:
            self._h = max(self.min_h, ch + top + bottom)
        if self.aspect:
            if self._explicit_w and not self._explicit_h:
                self._h = self._w / self.aspect
            elif self._explicit_h and not self._explicit_w:
                self._w = self._h * self.aspect
            elif not self._explicit_w and not self._explicit_h:
                if self._w / max(self._h, 1e-6) < self.aspect:
                    self._w = self._h * self.aspect
                else:
                    self._h = self._w / self.aspect
        self._place_content()

    def _inner_box(self) -> BBox:
        """The content area. Falls back to the whole shape when padding
        would leave no room — otherwise content drifts toward the padding
        instead of staying centred on a small shape."""
        top, right, bottom, left = self.padding()
        w = (self._w or 0) - left - right
        h = (self._h or 0) - top - bottom
        x, y = self._x + left, self._y + top
        if w <= 0:
            x, w = self._x, (self._w or 0)
        if h <= 0:
            y, h = self._y, (self._h or 0)
        return BBox(x, y, w, h)

    def _place_content(self) -> None:
        inner = self._inner_box()
        halign = str(self.prop("text_align", "center")).lower()
        valign = str(self.prop("valign", "center")).lower()
        items = [i for i in (self._content, self._label) if i is not None]
        if not items:
            return
        # Stack content above label when both are present.
        total_h = sum(i.local_bbox.h for i in items)
        y = _valign_start(inner, total_h, valign)
        for item in items:
            ib = item.local_bbox
            x = _halign_start(inner, ib.w, halign)
            if item is self._label:
                item._x = x if not self._label._wrap else inner.x
                if self._label._wrap and inner.w > 0:
                    item._w = inner.w
                item._y = y
                if valign in ("center", "middle", "c"):
                    lay = self._label.layout
                    band = max(0.0, lay.baseline_last - lay.cap_top)
                    item._y = inner.cy - band / 2.0 - lay.cap_top
                    if len(items) > 1:
                        item._y = y
            else:
                item.place_local(x, y, anchor="nw")
            y += ib.h

    # -- drawing ---------------------------------------------------------
    def shape_nodes(self, ctx: RenderContext, bb: BBox) -> list:
        raise NotImplementedError

    def path_data(self, bb: BBox = None) -> str:
        """Outline of the shape as SVG path data (used by some connectors)."""
        bb = bb or self.local_bbox
        return path_from_points(bb.corners, close=True)

    def _render_content(self, ctx: RenderContext):
        self._ensure()
        bb = self.local_bbox
        nodes = list(self.shape_nodes(ctx, bb) or [])
        if self._content is not None:
            n = self._content.render(ctx)
            if n is not None:
                nodes.append(n)
        if self._label is not None:
            n = self._label.render(ctx)
            if n is not None:
                nodes.append(n)
        return nodes or None


def _halign_start(inner: BBox, w: float, align: str) -> float:
    if align in ("left", "start", "w"):
        return inner.x
    if align in ("right", "end", "e"):
        return inner.x1 - w
    return inner.x + (inner.w - w) / 2.0


def _valign_start(inner: BBox, h: float, align: str) -> float:
    if align in ("top", "start", "n"):
        return inner.y
    if align in ("bottom", "end", "s"):
        return inner.y1 - h
    return inner.y + (inner.h - h) / 2.0


# ==========================================================================
# Rectangles
# ==========================================================================

class Box(Shape):
    """A rectangle with an optional label. The workhorse of most figures.

    >>> Box("Feature\\nExtractor", w=120, style="block")
    """

    role = "box"

    def _radius(self, bb: BBox) -> float:
        r = self.prop("radius", 0) or 0
        if isinstance(r, str):
            if r.lower() in ("pill", "full", "round"):
                return min(bb.w, bb.h) / 2.0
            r = float(r)
        return max(0.0, min(float(r), bb.w / 2.0, bb.h / 2.0))

    def shape_nodes(self, ctx: RenderContext, bb: BBox) -> list:
        attrs = paint_attrs(self, ctx, bbox=bb)
        r = self._radius(bb)
        node = Node("rect", x=bb.x, y=bb.y, width=bb.w, height=bb.h, **attrs)
        if r:
            node.set(rx=r, ry=r)
        return [node]

    def path_data(self, bb: BBox = None) -> str:
        bb = bb or self.local_bbox
        r = self._radius(bb)
        if not r:
            return path_from_points(bb.corners, close=True)
        return rounded_polyline(list(bb.corners), radius=r, close=True)


Rect = Box


class Pill(Box):
    """A fully rounded box (radius = half the height)."""

    def _radius(self, bb: BBox) -> float:
        r = self.prop("radius", None)
        if r is None or (isinstance(r, str) and r.lower() in ("pill", "full")):
            return min(bb.w, bb.h) / 2.0
        return super()._radius(bb)


Stadium = Pill


# ==========================================================================
# Ellipses
# ==========================================================================

class Ellipse(Shape):
    role = "ellipse"
    default_padding = (10, 18)

    def _measure(self) -> None:
        super()._measure()
        if self._label is not None and not (self._explicit_w and self._explicit_h):
            # a label needs sqrt(2) more room inside an ellipse than a box
            top, right, bottom, left = self.padding()
            cw, ch = self._inner_size()
            if not self._explicit_w:
                self._w = max(self.min_w, cw * 1.42 + left + right)
            if not self._explicit_h:
                self._h = max(self.min_h, ch * 1.42 + top + bottom)
            self._place_content()

    def shape_nodes(self, ctx: RenderContext, bb: BBox) -> list:
        attrs = paint_attrs(self, ctx, bbox=bb)
        return [Node("ellipse", cx=bb.cx, cy=bb.cy, rx=bb.w / 2.0,
                     ry=bb.h / 2.0, **attrs)]

    def anchor_point(self, name: str) -> Point:
        return self.bbox.at_angle({"e": 0, "se": 45, "s": 90, "sw": 135,
                                   "w": 180, "nw": 225, "n": 270,
                                   "ne": 315}.get(name, 0))

    def path_data(self, bb: BBox = None) -> str:
        bb = bb or self.local_bbox
        rx, ry = bb.w / 2.0, bb.h / 2.0
        return (f"M{fmt(bb.x)} {fmt(bb.cy)}"
                f"A{fmt(rx)} {fmt(ry)} 0 1 0 {fmt(bb.x1)} {fmt(bb.cy)}"
                f"A{fmt(rx)} {fmt(ry)} 0 1 0 {fmt(bb.x)} {fmt(bb.cy)}Z")


class Circle(Ellipse):
    """An ellipse constrained to a 1:1 aspect ratio."""

    def __init__(self, text=None, x=0.0, y=0.0, r: float = None, **kw):
        if r is not None:
            kw.setdefault("w", r * 2)
            kw.setdefault("h", r * 2)
        super().__init__(text, x, y, **kw)
        self.aspect = 1.0

    def _measure(self) -> None:
        super()._measure()
        if not (self._explicit_w and self._explicit_h):
            d = max(self._w or 0, self._h or 0)
            self._w = self._h = d
            self._place_content()

    @property
    def radius(self) -> float:
        return self.bbox.w / 2.0


# ==========================================================================
# Polygonal shapes
# ==========================================================================

class _PolyShape(Shape):
    """Shape defined by fractional ``(u, v)`` vertices inside its bbox."""

    role = "box"
    points_uv: tuple = ()
    inset = (0.0, 0.0)     # extra padding fraction (x, y) for the label

    def _measure(self) -> None:
        super()._measure()
        fx, fy = self.inset
        if self._label is not None and (fx or fy):
            if not self._explicit_w:
                self._w = self._w * (1 + fx)
            if not self._explicit_h:
                self._h = self._h * (1 + fy)
            self._place_content()

    def vertices(self, bb: BBox) -> list:
        return [bb.uv(u, v) for u, v in self.points_uv]

    def path_data(self, bb: BBox = None) -> str:
        bb = bb or self.local_bbox
        r = self.prop("radius", 0) or 0
        pts = self.vertices(bb)
        if r:
            return rounded_polyline(pts, radius=float(r), close=True)
        return path_from_points(pts, close=True)

    def shape_nodes(self, ctx: RenderContext, bb: BBox) -> list:
        attrs = paint_attrs(self, ctx, bbox=bb)
        return [Node("path", d=self.path_data(bb), **attrs)]


class Diamond(_PolyShape):
    points_uv = ((0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5))
    inset = (0.7, 0.7)


class Triangle(_PolyShape):
    points_uv = ((0.5, 0.0), (1.0, 1.0), (0.0, 1.0))
    inset = (0.5, 0.25)


class Hexagon(_PolyShape):
    points_uv = ((0.25, 0.0), (0.75, 0.0), (1.0, 0.5),
                 (0.75, 1.0), (0.25, 1.0), (0.0, 0.5))
    inset = (0.3, 0.0)


class Parallelogram(_PolyShape):
    points_uv = ((0.18, 0.0), (1.0, 0.0), (0.82, 1.0), (0.0, 1.0))
    inset = (0.25, 0.0)


class Chevron(_PolyShape):
    points_uv = ((0.0, 0.0), (0.82, 0.0), (1.0, 0.5), (0.82, 1.0),
                 (0.0, 1.0), (0.18, 0.5))
    inset = (0.3, 0.0)


class Star(_PolyShape):
    def __init__(self, text=None, x=0.0, y=0.0, points: int = 5,
                 inner: float = 0.42, **kw):
        self.n_points = int(points)
        self.inner_ratio = float(inner)
        super().__init__(text, x, y, **kw)
        if not self._explicit_w:
            self._w = self._w or 40
        if not self._explicit_h:
            self._h = self._h or 40

    def vertices(self, bb: BBox) -> list:
        pts = []
        n = self.n_points
        for i in range(2 * n):
            r = 1.0 if i % 2 == 0 else self.inner_ratio
            a = -math.pi / 2 + i * math.pi / n
            pts.append(Point(bb.cx + math.cos(a) * r * bb.w / 2,
                             bb.cy + math.sin(a) * r * bb.h / 2))
        return pts


class Cylinder(Shape):
    """Database / storage symbol."""

    role = "box"
    default_padding = (16, 14)

    def __init__(self, text=None, x=0.0, y=0.0, ellipse_h: float = None, **kw):
        self.ellipse_h = ellipse_h
        super().__init__(text, x, y, **kw)

    def _eh(self, bb: BBox) -> float:
        return (self.ellipse_h if self.ellipse_h is not None
                else min(bb.h * 0.22, bb.w * 0.3))

    def shape_nodes(self, ctx: RenderContext, bb: BBox) -> list:
        attrs = paint_attrs(self, ctx, bbox=bb)
        eh = self._eh(bb)
        rx, ry = bb.w / 2.0, eh / 2.0
        body = (f"M{fmt(bb.x)} {fmt(bb.y + ry)}"
                f"A{fmt(rx)} {fmt(ry)} 0 0 1 {fmt(bb.x1)} {fmt(bb.y + ry)}"
                f"L{fmt(bb.x1)} {fmt(bb.y1 - ry)}"
                f"A{fmt(rx)} {fmt(ry)} 0 0 1 {fmt(bb.x)} {fmt(bb.y1 - ry)}Z")
        top = (f"M{fmt(bb.x)} {fmt(bb.y + ry)}"
               f"A{fmt(rx)} {fmt(ry)} 0 0 0 {fmt(bb.x1)} {fmt(bb.y + ry)}")
        line_attrs = dict(attrs)
        line_attrs["fill"] = "none"
        return [Node("path", d=body, **attrs), Node("path", d=top, **line_attrs)]


class Note(Shape):
    """Document/note shape with a folded corner."""

    role = "box"

    def __init__(self, text=None, x=0.0, y=0.0, fold: float = 14.0, **kw):
        self.fold = float(fold)
        super().__init__(text, x, y, **kw)

    def shape_nodes(self, ctx: RenderContext, bb: BBox) -> list:
        attrs = paint_attrs(self, ctx, bbox=bb)
        f = min(self.fold, bb.w / 2, bb.h / 2)
        body = (f"M{fmt(bb.x)} {fmt(bb.y)}H{fmt(bb.x1 - f)}L{fmt(bb.x1)} "
                f"{fmt(bb.y + f)}V{fmt(bb.y1)}H{fmt(bb.x)}Z")
        fold = (f"M{fmt(bb.x1 - f)} {fmt(bb.y)}V{fmt(bb.y + f)}H{fmt(bb.x1)}")
        fold_attrs = dict(attrs)
        fold_attrs["fill"] = "none"
        return [Node("path", d=body, **attrs), Node("path", d=fold, **fold_attrs)]


# ==========================================================================
# Pure geometry
# ==========================================================================

class Path(Element):
    """A raw SVG path. Bounds are computed exactly from the path data."""

    role = "path"
    STROKE_WIDTH_ALIAS = True

    def __init__(self, d: str, x: float = None, y: float = None, **kw):
        self._d = d or ""
        x0, y0, x1, y1 = path_bbox(self._d)
        self._src = BBox.from_corners(x0, y0, x1, y1)
        self._scale = (1.0, 1.0)
        super().__init__(self._src.x if x is None else x,
                         self._src.y if y is None else y,
                         self._src.w, self._src.h, **kw)
        self._explicit_w = self._explicit_h = False

    @property
    def d(self) -> str:
        return self._d

    @d.setter
    def d(self, value: str) -> None:
        self._d = value or ""
        x0, y0, x1, y1 = path_bbox(self._d)
        self._src = BBox.from_corners(x0, y0, x1, y1)
        self._w, self._h = self._src.w, self._src.h
        self.invalidate()

    def _measure(self) -> None:
        self._w = self._src.w * self._scale[0]
        self._h = self._src.h * self._scale[1]

    def resize(self, w: float = None, h: float = None, anchor: str = "nw"):
        keep = self.bbox.anchor(anchor)
        sx = (w / self._src.w) if (w and self._src.w) else self._scale[0]
        sy = (h / self._src.h) if (h and self._src.h) else self._scale[1]
        if w and not h:
            sy = sx
        if h and not w:
            sx = sy
        self._scale = (sx, sy)
        self.invalidate()
        self._ensure()
        now = self.bbox.anchor(anchor)
        return self.move(keep.x - now.x, keep.y - now.y)

    def transformed_d(self) -> str:
        sx, sy = self._scale
        m = (Affine.translate(self._x, self._y) @ Affine.scale(sx, sy)
             @ Affine.translate(-self._src.x, -self._src.y))
        return self._d if m.is_identity else transform_path_data(self._d, m)

    def _render_content(self, ctx: RenderContext):
        self._ensure()
        attrs = paint_attrs(self, ctx, bbox=self.local_bbox)
        return Node("path", d=self.transformed_d(), **attrs)

    def path_data(self, bb: BBox = None) -> str:
        return self.transformed_d()


class Polyline(Element):
    """An open polyline through a list of points (optionally rounded).

    Points may be raw coordinates *or* live references (anchors/elements).
    With live references the polyline re-resolves them on every read, so it
    follows whatever it was attached to.
    """

    role = "path"
    closed = False
    STROKE_WIDTH_ALIAS = True

    def __init__(self, points, close: bool = None, **kw):
        self._refs = list(points)
        self._live = any(_is_live(p) for p in self._refs)
        self._points = [to_point(p) for p in self._refs]
        if close is not None:
            self.closed = bool(close)
        bb = BBox.from_points(self._points)
        super().__init__(bb.x, bb.y, bb.w, bb.h, **kw)
        self._src = bb
        self._explicit_w = self._explicit_h = False

    @property
    def live(self) -> bool:
        return self._live

    @property
    def points(self) -> list:
        if self._live:
            return [to_point(r) for r in self._refs]
        off = Point(self._x - self._src.x, self._y - self._src.y)
        return [p + off for p in self._points]

    @points.setter
    def points(self, value) -> None:
        self._refs = list(value)
        self._live = any(_is_live(p) for p in self._refs)
        self._points = [to_point(p) for p in self._refs]
        self._src = BBox.from_points(self._points)
        self._x, self._y = self._src.x, self._src.y
        self.invalidate()

    def _measure(self) -> None:
        if self._live:
            bb = BBox.from_points(self.points)
            self._x, self._y, self._w, self._h = bb.x, bb.y, bb.w, bb.h
        else:
            self._w, self._h = self._src.w, self._src.h

    @property
    def local_bbox(self) -> BBox:
        if self._live:
            self._dirty = True      # endpoints may have moved
        self._ensure()
        return BBox(self._x, self._y, self._w or 0.0, self._h or 0.0)

    def resize(self, w: float = None, h: float = None, anchor: str = "nw"):
        """Scale the point set (only meaningful for static polylines)."""
        if self._live or not self._src.w or not self._src.h:
            return self
        keep = self.bbox.anchor(anchor)
        sx = (w / self._src.w) if w else 1.0
        sy = (h / self._src.h) if h else 1.0
        if w and not h:
            sy = sx
        if h and not w:
            sx = sy
        ox, oy = self._src.x, self._src.y
        self._points = [Point(ox + (p.x - ox) * sx, oy + (p.y - oy) * sy)
                        for p in self._points]
        self._src = BBox.from_points(self._points)
        self.invalidate()
        self._ensure()
        now = self.bbox.anchor(anchor)
        return self.move(keep.x - now.x, keep.y - now.y)

    def path_data(self, bb: BBox = None) -> str:
        r = self.prop("radius", 0) or 0
        pts = self.points
        if r:
            return rounded_polyline(pts, float(r), close=self.closed)
        return path_from_points(pts, close=self.closed)

    def _render_content(self, ctx: RenderContext):
        self._ensure()
        attrs = paint_attrs(self, ctx, bbox=self.local_bbox)
        if not self.closed:
            attrs["fill"] = attrs.get("fill", "none")
            if self.prop("fill", None) is None:
                attrs["fill"] = "none"
        return Node("path", d=self.path_data(), **attrs)


class Polygon(Polyline):
    """A closed polyline."""

    role = "box"
    closed = True


class Line(Polyline):
    """A straight segment between two points, anchors or elements."""

    role = "line"

    def __init__(self, start, end, **kw):
        super().__init__([start, end], **kw)

    @property
    def start(self) -> Point:
        return self.points[0]

    @property
    def end(self) -> Point:
        return self.points[1]


def _is_live(obj) -> bool:
    """True if ``obj`` resolves to a different point when things move."""
    from .core import Anchor
    return isinstance(obj, (Anchor, Element))


class Dot(Element):
    """A small filled circle — plot markers, junction points, bullets."""

    role = "marker"

    def __init__(self, center=(0, 0), r: float = 3.0, **kw):
        p = to_point(center)
        self._r = float(r)
        super().__init__(p.x - r, p.y - r, r * 2, r * 2, **kw)

    @property
    def r(self) -> float:
        return self.bbox.w / 2.0

    def _measure(self) -> None:
        if self._w is None:
            self._w = self._r * 2
        if self._h is None:
            self._h = self._r * 2

    def _render_content(self, ctx: RenderContext):
        self._ensure()
        bb = self.local_bbox
        attrs = paint_attrs(self, ctx, bbox=bb)
        return Node("ellipse", cx=bb.cx, cy=bb.cy, rx=bb.w / 2,
                    ry=bb.h / 2, **attrs)


class Marker(Element):
    """A plot marker: circle, square, diamond, triangle, cross, plus, x."""

    role = "marker"
    SHAPES = ("circle", "square", "diamond", "triangle", "cross", "plus",
              "x", "star")

    def __init__(self, center=(0, 0), size: float = 7.0, shape: str = "circle",
                 **kw):
        p = to_point(center)
        self.shape = str(shape).lower()
        super().__init__(p.x - size / 2, p.y - size / 2, size, size, **kw)

    def _render_content(self, ctx: RenderContext):
        self._ensure()
        bb = self.local_bbox
        attrs = paint_attrs(self, ctx, bbox=bb)
        s = self.shape
        if s == "circle":
            return Node("ellipse", cx=bb.cx, cy=bb.cy, rx=bb.w / 2,
                        ry=bb.h / 2, **attrs)
        if s == "square":
            return Node("rect", x=bb.x, y=bb.y, width=bb.w, height=bb.h, **attrs)
        if s in ("cross", "plus", "x"):
            line_attrs = dict(attrs)
            line_attrs["fill"] = "none"
            if line_attrs.get("stroke", "none") == "none":
                line_attrs["stroke"] = self.prop("fill", "#000")
                line_attrs.setdefault("stroke-width",
                                      self.prop("stroke_width", 1.5) or 1.5)
            if s == "plus":
                d = (f"M{fmt(bb.x)} {fmt(bb.cy)}H{fmt(bb.x1)}"
                     f"M{fmt(bb.cx)} {fmt(bb.y)}V{fmt(bb.y1)}")
            else:
                d = (f"M{fmt(bb.x)} {fmt(bb.y)}L{fmt(bb.x1)} {fmt(bb.y1)}"
                     f"M{fmt(bb.x1)} {fmt(bb.y)}L{fmt(bb.x)} {fmt(bb.y1)}")
            return Node("path", d=d, **line_attrs)
        uv = {"diamond": ((0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)),
              "triangle": ((0.5, 0), (1, 1), (0, 1))}.get(s)
        if uv:
            return Node("path", d=path_from_points([bb.uv(*p) for p in uv],
                                                   close=True), **attrs)
        pts = []
        for i in range(10):
            r = 1.0 if i % 2 == 0 else 0.45
            a = -math.pi / 2 + i * math.pi / 5
            pts.append(Point(bb.cx + math.cos(a) * r * bb.w / 2,
                             bb.cy + math.sin(a) * r * bb.h / 2))
        return Node("path", d=path_from_points(pts, close=True), **attrs)
