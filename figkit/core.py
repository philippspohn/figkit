"""The element model: live anchors, relative placement, groups, z-order."""

from __future__ import annotations

import contextvars
import copy as _copy
import itertools
from typing import Iterable

from .geom import (Affine, BBox, Point, _expand_spec, anchor_normal, to_point)
from .style import (DEFAULT_THEME, FALLBACKS, INHERITED, Style, Theme,
                    current_theme, normalize_key)
from .svgdoc import Node, RenderContext

__all__ = ["Anchor", "Element", "Group", "active_container",
           "split_classes", "MISSING"]


class _Missing:
    def __repr__(self):
        return "MISSING"


MISSING = _Missing()

# Containers that auto-adopt newly created elements (populated by
# ``with Figure() as fig:``).  A ContextVar rather than a module global so two
# threads — or two asyncio tasks — can build figures at the same time without
# stealing each other's elements.
_container_var: contextvars.ContextVar = contextvars.ContextVar(
    "figkit_containers", default=())


def active_container():
    """The innermost container currently collecting new elements."""
    stack = _container_var.get()
    return stack[-1] if stack else None


def push_container(container):
    """Start collecting into ``container``; returns a token for :func:`pop_container`."""
    return _container_var.set(_container_var.get() + (container,))


def pop_container(token=None):
    if token is not None:
        _container_var.reset(token)
        return
    stack = _container_var.get()
    if stack:
        _container_var.set(stack[:-1])


_id_counter = itertools.count(1)


def split_classes(value) -> tuple:
    """Normalise ``"a b"`` / ``[".a", "b"]`` into ``("a", "b")``."""
    if value is None:
        return ()
    if isinstance(value, str):
        parts = value.split()
    else:
        parts = list(value)
    return tuple(str(p).lstrip(".") for p in parts if str(p).strip())


# ==========================================================================
# Anchors
# ==========================================================================

class Anchor:
    """A *live* reference to a point on an element.

    Resolved on read, so moving the element updates every arrow that points at
    it.  Anchors support ``+``/``-`` with ``(dx, dy)`` to make offset anchors.
    """

    __slots__ = ("element", "name", "_uv", "_angle", "dx", "dy")

    def __init__(self, element, name: str = None, uv=None, angle: float = None,
                 dx: float = 0.0, dy: float = 0.0):
        self.element = element
        self.name = name
        self._uv = uv
        self._angle = angle
        self.dx = dx
        self.dy = dy

    @property
    def point(self) -> Point:
        bb = self.element.bbox
        if self._uv is not None:
            p = bb.uv(self._uv[0], self._uv[1])
        elif self._angle is not None:
            p = bb.at_angle(self._angle)
        else:
            p = bb.anchor(self.name or "center")
        return Point(p.x + self.dx, p.y + self.dy)

    # -- convenience ----------------------------------------------------
    @property
    def x(self) -> float:
        return self.point.x

    @property
    def y(self) -> float:
        return self.point.y

    @property
    def normal(self) -> Point:
        """Outward direction at this anchor (used to shape connectors)."""
        if self.name:
            n = anchor_normal(self.name)
            if n.length:
                return n
        if self._angle is not None:
            import math
            a = math.radians(self._angle)
            return Point(math.cos(a), math.sin(a))
        if self._uv is not None:
            u, v = self._uv
            nx = -1.0 if u <= 0.01 else (1.0 if u >= 0.99 else 0.0)
            ny = -1.0 if v <= 0.01 else (1.0 if v >= 0.99 else 0.0)
            p = Point(nx, ny)
            if p.length:
                return p.normalized()
        return Point(0.0, 0.0)

    def offset(self, dx: float = 0.0, dy: float = 0.0) -> "Anchor":
        return Anchor(self.element, self.name, self._uv, self._angle,
                      self.dx + dx, self.dy + dy)

    def __add__(self, delta) -> "Anchor":
        d = to_point(delta)
        return self.offset(d.x, d.y)

    def __sub__(self, delta) -> "Anchor":
        d = to_point(delta)
        return self.offset(-d.x, -d.y)

    def __iter__(self):
        return iter(self.point)

    def __getitem__(self, i):
        return self.point[i]

    def __repr__(self) -> str:
        what = self.name or (f"uv{self._uv}" if self._uv else f"@{self._angle}")
        return f"<Anchor {what} of {type(self.element).__name__} -> {self.point}>"


# ==========================================================================
# Element
# ==========================================================================

class Element:
    """Base class for everything drawable.

    Subclasses implement :meth:`_measure` (to set ``_w``/``_h`` when the size
    is intrinsic) and :meth:`_render_content` (to emit SVG nodes).
    """

    role = "element"

    #: line-like elements have no geometric width, so ``width=`` means stroke
    STROKE_WIDTH_ALIAS = False

    def __init__(self, x: float = 0.0, y: float = 0.0, w: float = None,
                 h: float = None, *, style=None, classes=(), theme: Theme = None,
                 name: str = None, z: float = 0.0, visible: bool = True,
                 opacity: float = None, transform: Affine = None,
                 rotate: float = None, rotate_about=None,
                 clip: bool = False, audit: bool = True, add: bool = None,
                 **props):
        self._x = float(x)
        self._y = float(y)
        self._w = None if w is None else float(w)
        self._h = None if h is None else float(h)
        self._explicit_w = w is not None
        self._explicit_h = h is not None
        self._transform = transform or Affine.IDENTITY
        self.parent = None
        self.name = name
        self.z = z
        self._visible = bool(visible)
        self.clip = clip
        #: set False to exempt this element from :meth:`Figure.audit`
        self.audit_enabled = bool(audit)
        self.uid = f"e{next(_id_counter)}"
        self._theme = theme
        self._ambient_theme = current_theme()
        self._raw_style = style
        self.classes: tuple = split_classes(classes)
        self._style = Style()
        self._extra_props = props
        if opacity is not None:
            props = dict(props, opacity=opacity)
            self._extra_props = props
        self._dirty = True
        self._bbox_cache = None
        self._set_style(style, props)
        # Deferred: at this point a subclass has not finished __init__, so an
        # auto-sized element does not know how big it is yet and a label-sized
        # one has no label. Rotating now would pivot on the placeholder box and
        # land the element somewhere that depends on how long its text is.
        self._pending_rotate = (rotate, rotate_about) if rotate else None
        container = active_container()
        if add is None:
            add = container is not None
        if add and container is not None:
            container.add(self)

    # -- style plumbing --------------------------------------------------
    def _set_style(self, style, props: dict) -> None:
        """Split ``style=`` into class names (lazy) and literal styles (eager)."""
        if self.STROKE_WIDTH_ALIAS and "width" in props:
            props = dict(props)
            props.setdefault("stroke_width", props.pop("width"))
        resolved = []
        for item in (style if isinstance(style, (list, tuple)) else [style]):
            if item is None:
                continue
            if isinstance(item, str):
                self.classes = self.classes + split_classes(item)
            else:
                resolved.append(item)
        self._style = Style(*resolved, **props)
        self.invalidate()

    def class_style(self, name: str) -> Style | None:
        """The style a class name resolves to in this element's theme chain."""
        key = str(name).lstrip(".")
        for th in self.theme_chain():
            if key in th.styles:
                return th.styles[key]
        return None

    def add_class(self, *names) -> "Element":
        """Add style classes (later classes win over earlier ones)."""
        for name in names:
            self.classes = self.classes + split_classes(name)
        return self.invalidate()

    def remove_class(self, *names) -> "Element":
        drop = set()
        for name in names:
            drop.update(split_classes(name))
        self.classes = tuple(c for c in self.classes if c not in drop)
        return self.invalidate()

    def has_class(self, name: str) -> bool:
        return str(name).lstrip(".") in self.classes

    def restyle(self, *styles, **props) -> "Element":
        """Merge more style on top of this element's own style.

        String arguments are treated as class names.
        """
        if self.STROKE_WIDTH_ALIAS and "width" in props:
            props = dict(props)
            props.setdefault("stroke_width", props.pop("width"))
        merged = [self._style]
        for item in styles:
            if isinstance(item, str):
                self.add_class(item)
            elif item is not None:
                merged.append(item)
        self._style = Style(*merged, **props)
        self.invalidate()
        return self

    @property
    def style(self) -> Style:
        return self._style

    @style.setter
    def style(self, value) -> None:
        self._set_style(value, {})

    @property
    def theme(self) -> Theme:
        for th in self.theme_chain():
            return th
        return DEFAULT_THEME

    @theme.setter
    def theme(self, value) -> None:
        self._theme = value if isinstance(value, Theme) or value is None else Theme(value)
        self.invalidate()

    def theme_chain(self) -> Iterable[Theme]:
        """Themes from innermost to outermost, ending with the default.

        Own theme, then each ancestor's, then the theme that was ambient when
        this element was constructed, then the built-in default.
        """
        if self._theme is not None:
            yield self._theme
        node = self.parent
        while node is not None:
            th = getattr(node, "_theme", None)
            if th is not None:
                yield th
            node = getattr(node, "parent", None)
        if self._ambient_theme is not None:
            yield self._ambient_theme
        yield DEFAULT_THEME

    def prop(self, name: str, default=MISSING, role: str = None):
        """Resolve a style property through the whole cascade."""
        key = normalize_key(name)
        if key in self._style:
            return self._resolve_value(self._style[key])
        for class_name in reversed(self.classes):     # later classes win
            cls = self.class_style(class_name)
            if cls is not None and key in cls:
                return self._resolve_value(cls[key])
        if key in INHERITED:
            node = self.parent
            while node is not None:
                st = getattr(node, "_style", None)
                if st is not None and key in st:
                    return self._resolve_value(st[key])
                node = getattr(node, "parent", None)
        role = role or self.role
        for th in self.theme_chain():
            value, found = th.lookup(key, role)
            if found:
                return self._resolve_value(value)
        if default is not MISSING:
            return default
        return FALLBACKS.get(key)

    def _resolve_value(self, value):
        if isinstance(value, str) and value.startswith("@"):
            for th in self.theme_chain():
                if value[1:] in th.palette:
                    return th.palette[value[1:]]
            return value[1:]
        return value

    def padding(self) -> tuple:
        return _expand_spec(self.prop("padding", 0))

    # -- geometry --------------------------------------------------------
    def _measure(self) -> None:
        """Subclasses set ``self._w``/``self._h`` when size is intrinsic."""
        if self._w is None:
            self._w = 0.0
        if self._h is None:
            self._h = 0.0

    def _ensure(self) -> None:
        if self._dirty:
            self._dirty = False
            self._measure()

    def _apply_pending_rotate(self) -> None:
        """Run a constructor ``rotate=`` now that the element has a size."""
        pending = getattr(self, "_pending_rotate", None)
        if pending is None:
            return
        self._pending_rotate = None          # before rotating: it reads bbox
        self.rotate(pending[0], about=pending[1])

    def invalidate(self) -> "Element":
        self._dirty = True
        self._bbox_cache = None
        node = self.parent
        while node is not None:
            node._bbox_cache = None
            node = getattr(node, "parent", None)
        return self

    def parent_matrix(self) -> Affine:
        return self.parent.child_matrix() if self.parent is not None else Affine.IDENTITY

    def child_matrix(self) -> Affine:
        """Matrix that maps a child's coordinates into world space."""
        return self.world_matrix()

    def world_matrix(self) -> Affine:
        return self.parent_matrix() @ self._transform

    @property
    def local_bbox(self) -> BBox:
        """Bounds in the element's own (pre-transform) coordinates."""
        self._apply_pending_rotate()
        self._ensure()
        return BBox(self._x, self._y, self._w or 0.0, self._h or 0.0)

    @property
    def bbox(self) -> BBox:
        """Bounds in world (figure) coordinates. Anchors read this."""
        # Before world_matrix(): a deferred rotation is what puts the rotation
        # *into* that matrix, so reading it first would return a stale one.
        self._apply_pending_rotate()
        m = self.world_matrix()
        lb = self.local_bbox
        return lb if m.is_identity else m.apply_bbox(lb)

    @property
    def ink_bbox(self) -> BBox:
        """Bounds including stroke width — used for auto-sizing the canvas."""
        bb = self.bbox
        sw = self.prop("stroke_width", 0) or 0
        has_stroke = self.prop("stroke", None) not in (None, "none")
        return bb.expand(sw / 2.0) if has_stroke and sw else bb

    @property
    def x(self) -> float:
        return self.bbox.x

    @property
    def y(self) -> float:
        return self.bbox.y

    @property
    def width(self) -> float:
        return self.bbox.w

    @property
    def height(self) -> float:
        return self.bbox.h

    @property
    def size(self) -> Point:
        bb = self.bbox
        return Point(bb.w, bb.h)

    def resize(self, w: float = None, h: float = None,
               anchor: str = "nw") -> "Element":
        """Set an explicit size, keeping ``anchor`` fixed in place."""
        keep = self.bbox.anchor(anchor)
        if w is not None:
            self._w = float(w)
            self._explicit_w = True
        if h is not None:
            self._h = float(h)
            self._explicit_h = True
        self._dirty = True
        self.invalidate()
        now = self.bbox.anchor(anchor)
        return self.move(keep.x - now.x, keep.y - now.y)

    def grow(self, dw: float = 0.0, dh: float = 0.0,
             anchor: str = "center") -> "Element":
        bb = self.bbox
        return self.resize(bb.w + dw, bb.h + dh, anchor=anchor)

    # -- movement --------------------------------------------------------
    def _to_local_delta(self, dx: float, dy: float) -> Point:
        m = self.world_matrix()
        if m.is_identity:
            return Point(dx, dy)
        inv = m.inverse()
        return inv.apply((dx, dy)) - inv.apply((0.0, 0.0))

    def move(self, dx: float = 0.0, dy: float = 0.0) -> "Element":
        """Translate by ``(dx, dy)`` in world units."""
        d = self._to_local_delta(dx, dy)
        self._x += d.x
        self._y += d.y
        self.invalidate()
        return self

    def at(self, x=None, y=None, anchor: str = "nw") -> "Element":
        """Place ``anchor`` of this element at world position ``(x, y)``.

        ``at((x, y))`` and ``at(some_anchor)`` also work.
        """
        if y is None and x is not None and not isinstance(x, (int, float)):
            p = to_point(x)
            x, y = p.x, p.y
        cur = self.bbox.anchor(anchor)
        dx = 0.0 if x is None else float(x) - cur.x
        dy = 0.0 if y is None else float(y) - cur.y
        return self.move(dx, dy)

    def center_at(self, x=None, y=None) -> "Element":
        return self.at(x, y, anchor="center")

    def place_local(self, x: float, y: float, anchor: str = "nw") -> "Element":
        """Like :meth:`at`, but in the parent's own (pre-transform) space.

        Used by containers to position their internal labels: their geometry is
        computed in local coordinates, so going through world space and back
        would be wrong whenever a transform is in play.
        """
        lb = self.local_bbox
        cur = lb.anchor(anchor)
        self._x += float(x) - cur.x
        self._y += float(y) - cur.y
        self.invalidate()
        return self

    def set_x(self, x: float, anchor: str = "nw") -> "Element":
        return self.at(x, None, anchor=anchor)

    def set_y(self, y: float, anchor: str = "nw") -> "Element":
        return self.at(None, y, anchor=anchor)

    # -- relative placement ----------------------------------------------
    def _align_axis(self, other, align, horizontal: bool) -> float:
        """Delta on the cross axis so ``align`` edges line up."""
        if align is None:
            return 0.0
        a = str(align).lower()
        mine, theirs = self.bbox, _bbox_of(other)
        if horizontal:   # placing left/right -> align vertically
            table = {"top": (mine.y0, theirs.y0), "n": (mine.y0, theirs.y0),
                     "bottom": (mine.y1, theirs.y1), "s": (mine.y1, theirs.y1),
                     "center": (mine.cy, theirs.cy), "middle": (mine.cy, theirs.cy),
                     "c": (mine.cy, theirs.cy)}
        else:            # placing above/below -> align horizontally
            table = {"left": (mine.x0, theirs.x0), "w": (mine.x0, theirs.x0),
                     "right": (mine.x1, theirs.x1), "e": (mine.x1, theirs.x1),
                     "center": (mine.cx, theirs.cx), "middle": (mine.cx, theirs.cx),
                     "c": (mine.cx, theirs.cx)}
        if a not in table:
            raise ValueError(
                f"align={align!r} is not valid here; use "
                f"{sorted(k for k in table if len(k) > 1)}")
        cur, target = table[a]
        return target - cur

    def right_of(self, other, gap: float = 0.0, align: str = "center",
                 dx: float = 0.0, dy: float = 0.0) -> "Element":
        """Put this element to the right of ``other`` with a ``gap``."""
        ob = _bbox_of(other)
        mine = self.bbox
        d = self._align_axis(other, align, horizontal=True)
        return self.move(ob.x1 + gap - mine.x0 + dx, d + dy)

    def left_of(self, other, gap: float = 0.0, align: str = "center",
                dx: float = 0.0, dy: float = 0.0) -> "Element":
        ob = _bbox_of(other)
        mine = self.bbox
        d = self._align_axis(other, align, horizontal=True)
        return self.move(ob.x0 - gap - mine.x1 + dx, d + dy)

    def below_of(self, other, gap: float = 0.0, align: str = "center",
                 dx: float = 0.0, dy: float = 0.0) -> "Element":
        ob = _bbox_of(other)
        mine = self.bbox
        d = self._align_axis(other, align, horizontal=False)
        return self.move(d + dx, ob.y1 + gap - mine.y0 + dy)

    def above_of(self, other, gap: float = 0.0, align: str = "center",
                 dx: float = 0.0, dy: float = 0.0) -> "Element":
        ob = _bbox_of(other)
        mine = self.bbox
        d = self._align_axis(other, align, horizontal=False)
        return self.move(d + dx, ob.y0 - gap - mine.y1 + dy)

    below = below_of
    above = above_of

    def next_to(self, other, side: str = "right", gap: float = 0.0,
                align: str = "center", dx: float = 0.0, dy: float = 0.0):
        fn = {"right": self.right_of, "e": self.right_of,
              "left": self.left_of, "w": self.left_of,
              "below": self.below_of, "s": self.below_of, "under": self.below_of,
              "above": self.above_of, "n": self.above_of, "over": self.above_of}
        key = str(side).lower()
        if key not in fn:
            raise ValueError(f"side={side!r}; use right/left/above/below")
        return fn[key](other, gap=gap, align=align, dx=dx, dy=dy)

    def inside(self, other, anchor: str = "center", pad=0.0,
               dx: float = 0.0, dy: float = 0.0) -> "Element":
        """Place this element inside ``other``, aligned to ``anchor``."""
        ob = _bbox_of(other).shrink(pad)
        target = ob.anchor(anchor)
        return self.at(target.x + dx, target.y + dy, anchor=anchor)

    def align_to(self, other, edge: str = "center") -> "Element":
        """Snap one edge (or centre axis) to match ``other``."""
        ob = _bbox_of(other)
        mine = self.bbox
        e = str(edge).lower()
        moves = {
            "left": (ob.x0 - mine.x0, 0.0), "w": (ob.x0 - mine.x0, 0.0),
            "right": (ob.x1 - mine.x1, 0.0), "e": (ob.x1 - mine.x1, 0.0),
            "top": (0.0, ob.y0 - mine.y0), "n": (0.0, ob.y0 - mine.y0),
            "bottom": (0.0, ob.y1 - mine.y1), "s": (0.0, ob.y1 - mine.y1),
            "center_x": (ob.cx - mine.cx, 0.0), "cx": (ob.cx - mine.cx, 0.0),
            "center_y": (0.0, ob.cy - mine.cy), "cy": (0.0, ob.cy - mine.cy),
            "center": (ob.cx - mine.cx, ob.cy - mine.cy),
        }
        if e not in moves:
            raise ValueError(f"edge={edge!r} is not a valid alignment edge")
        return self.move(*moves[e])

    def span_x(self, a, b, pad: float = 0.0) -> "Element":
        """Stretch horizontally to span from ``a`` to ``b`` (elements/points)."""
        x0 = min(_bbox_of(a).x0, _bbox_of(b).x0) - pad
        x1 = max(_bbox_of(a).x1, _bbox_of(b).x1) + pad
        self.resize(w=x1 - x0)
        return self.at(x0, None, anchor="nw")

    def span_y(self, a, b, pad: float = 0.0) -> "Element":
        y0 = min(_bbox_of(a).y0, _bbox_of(b).y0) - pad
        y1 = max(_bbox_of(a).y1, _bbox_of(b).y1) + pad
        self.resize(h=y1 - y0)
        return self.at(None, y0, anchor="nw")

    # -- transforms ------------------------------------------------------
    def rotate(self, deg: float, about=None) -> "Element":
        """Rotate around ``about`` (default: the element's own centre)."""
        pivot = self.bbox.center if about is None else to_point(about)
        inv = self.parent_matrix().inverse()
        local_pivot = inv.apply(pivot)
        self._transform = Affine.rotate(deg, local_pivot) @ self._transform
        return self.invalidate()

    def scale_by(self, sx: float, sy: float = None, about=None) -> "Element":
        pivot = self.bbox.center if about is None else to_point(about)
        inv = self.parent_matrix().inverse()
        p = inv.apply(pivot)
        sy = sx if sy is None else sy
        m = (Affine.translate(p.x, p.y) @ Affine.scale(sx, sy)
             @ Affine.translate(-p.x, -p.y))
        self._transform = m @ self._transform
        return self.invalidate()

    def flip_h(self, about=None) -> "Element":
        return self.scale_by(-1, 1, about)

    def flip_v(self, about=None) -> "Element":
        return self.scale_by(1, -1, about)

    def reset_transform(self) -> "Element":
        self._transform = Affine.IDENTITY
        return self.invalidate()

    # -- anchors ---------------------------------------------------------
    def anchor(self, name: str) -> Anchor:
        return Anchor(self, name=name)

    def uv(self, u: float, v: float) -> Anchor:
        """Anchor at a fractional position inside the bounding box."""
        return Anchor(self, uv=(float(u), float(v)))

    pt = uv

    def at_angle(self, deg: float) -> Anchor:
        """Anchor on the border along a ray from the centre (0 = east, cw)."""
        return Anchor(self, angle=float(deg))

    @property
    def n(self) -> Anchor:
        return Anchor(self, "n")

    @property
    def s(self) -> Anchor:
        return Anchor(self, "s")

    @property
    def e(self) -> Anchor:
        return Anchor(self, "e")

    @property
    def w(self) -> Anchor:
        return Anchor(self, "w")

    @property
    def ne(self) -> Anchor:
        return Anchor(self, "ne")

    @property
    def nw(self) -> Anchor:
        return Anchor(self, "nw")

    @property
    def se(self) -> Anchor:
        return Anchor(self, "se")

    @property
    def sw(self) -> Anchor:
        return Anchor(self, "sw")

    @property
    def center(self) -> Anchor:
        return Anchor(self, "center")

    c = center

    @property
    def top(self) -> Anchor:
        return Anchor(self, "n")

    @property
    def bottom(self) -> Anchor:
        return Anchor(self, "s")

    @property
    def left(self) -> Anchor:
        return Anchor(self, "w")

    @property
    def right(self) -> Anchor:
        return Anchor(self, "e")

    @property
    def point(self) -> Point:
        """An element used where a point is expected means its centre."""
        return self.bbox.center

    # -- tree ------------------------------------------------------------
    def to_front(self) -> "Element":
        if self.parent is not None:
            self.parent.raise_child(self)
        return self

    def to_back(self) -> "Element":
        if self.parent is not None:
            self.parent.lower_child(self)
        return self

    def remove(self) -> "Element":
        if self.parent is not None:
            self.parent.remove_child(self)
        return self

    def detach(self) -> "Element":
        return self.remove()

    def copy(self, **overrides) -> "Element":
        """Deep copy, detached from any parent."""
        clone = _copy.deepcopy(self, {id(self.parent): None})
        clone.parent = None
        clone.uid = f"e{next(_id_counter)}"
        if overrides:
            clone.restyle(**overrides)
        clone.invalidate()
        container = active_container()
        if container is not None:
            container.add(clone)
        return clone

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value) -> None:
        self._visible = bool(value)
        self.invalidate()

    def ignore_audit(self) -> "Element":
        """Exempt this element from :meth:`figkit.Figure.audit` checks."""
        self.audit_enabled = False
        return self

    def hide(self) -> "Element":
        """Keep the element but stop drawing it (and stop it affecting bounds)."""
        self.visible = False
        return self

    def show(self) -> "Element":
        self.visible = True
        return self

    def descendants(self):
        yield self

    def find(self, name: str):
        for el in self.descendants():
            if getattr(el, "name", None) == name:
                return el
        return None

    # -- rendering -------------------------------------------------------
    def _render_content(self, ctx: RenderContext):
        raise NotImplementedError

    def _wrapper_attrs(self, ctx: RenderContext) -> dict:
        attrs = {}
        if self.classes:
            attrs["class"] = " ".join(self.classes)
        if not self._transform.is_identity:
            attrs["transform"] = self._transform.to_svg()
        op = self.prop("opacity", None)
        if op is not None and float(op) != 1.0:
            attrs["opacity"] = float(op)
        if self.name:
            attrs["data-name"] = self.name
        return attrs

    def render(self, ctx: RenderContext) -> Node | None:
        if not self.visible:
            return None
        for class_name in self.classes:
            if self.class_style(class_name) is None:
                ctx.warn(f"unknown style class {class_name!r} on "
                         f"{type(self).__name__}")
        self._ensure()
        content = self._render_content(ctx)
        if content is None:
            return None
        nodes = content if isinstance(content, (list, tuple)) else [content]
        nodes = [n for n in nodes if n is not None]
        if not nodes:
            return None
        attrs = self._wrapper_attrs(ctx)
        if len(nodes) == 1 and not attrs:
            return nodes[0]
        if len(nodes) == 1 and set(attrs) <= {"transform", "opacity", "data-name"} \
                and nodes[0].tag not in ("text",):
            node = nodes[0]
            if "transform" in attrs and "transform" not in node.attrs:
                node.attrs.update(attrs)
                return node
            if "transform" not in attrs:
                node.attrs.update(attrs)
                return node
        g = Node("g", **attrs)
        g.add(*nodes)
        return g

    # -- misc ------------------------------------------------------------
    def __repr__(self) -> str:
        bb = self.bbox
        label = f" {self.name!r}" if self.name else ""
        return (f"<{type(self).__name__}{label} x={bb.x:.4g} y={bb.y:.4g} "
                f"w={bb.w:.4g} h={bb.h:.4g}>")


def _bbox_of(obj) -> BBox:
    """BBox of an element, anchor, point or raw bbox."""
    if isinstance(obj, BBox):
        return obj
    bb = getattr(obj, "bbox", None)
    if isinstance(bb, BBox):
        return bb
    p = to_point(obj)
    return BBox(p.x, p.y, 0.0, 0.0)


# ==========================================================================
# Group
# ==========================================================================

class Group(Element):
    """A container whose bounds follow its children.

    Groups are placeable like any other element (``group.right_of(box)``),
    can carry a style that cascades text properties down, and can carry a
    theme that cascades everything.
    """

    role = "group"

    def __init__(self, *children, style=None, classes=(), theme=None, name=None,
                 z=0.0, visible=True, opacity=None, clip=False, audit=True,
                 add=None, **props):
        self._children: list = []
        super().__init__(0, 0, None, None, style=style, classes=classes,
                         theme=theme, name=name, z=z, visible=visible,
                         opacity=opacity, clip=clip, audit=audit, add=add,
                         **props)
        flat = []
        for c in children:
            if c is None:
                continue
            if isinstance(c, (list, tuple)):
                flat.extend(x for x in c if x is not None)
            else:
                flat.append(c)
        for c in flat:
            self.add(c)

    # -- children --------------------------------------------------------
    @property
    def children(self) -> list:
        return list(self._children)

    def add(self, *elements) -> "Group":
        for el in elements:
            if el is None:
                continue
            if isinstance(el, (list, tuple)):
                self.add(*el)
                continue
            if el is self:
                raise ValueError("a group cannot contain itself")
            if el.parent is not None and el.parent is not self:
                el.parent.remove_child(el)
            if el in self._children:
                continue
            el.parent = self
            self._children.append(el)
            el.invalidate()
        self.invalidate()
        return self

    def extend(self, elements) -> "Group":
        return self.add(*elements)

    def remove_child(self, el) -> "Group":
        if el in self._children:
            self._children.remove(el)
            el.parent = None
            el.invalidate()
        self.invalidate()
        return self

    def clear(self) -> "Group":
        for el in list(self._children):
            self.remove_child(el)
        return self

    def raise_child(self, el) -> "Group":
        if el in self._children:
            self._children.remove(el)
            self._children.append(el)
        return self

    def lower_child(self, el) -> "Group":
        if el in self._children:
            self._children.remove(el)
            self._children.insert(0, el)
        return self

    def __iter__(self):
        return iter(self._children)

    def __len__(self) -> int:
        return len(self._children)

    def __getitem__(self, i):
        if isinstance(i, str):
            found = self.find(i)
            if found is None:
                raise KeyError(i)
            return found
        return self._children[i]

    def descendants(self):
        yield self
        for c in self._children:
            yield from c.descendants()

    # -- geometry --------------------------------------------------------
    def child_matrix(self) -> Affine:
        return self.world_matrix()

    @property
    def local_bbox(self) -> BBox:
        """World bounds mapped back into the group's own coordinate space."""
        self._apply_pending_rotate()
        world = self.bbox_from_children()
        m = self.world_matrix()
        return world if m.is_identity else m.inverse().apply_bbox(world)

    def bbox_from_children(self) -> BBox:
        boxes = [c.bbox for c in self._children if c.visible]
        bb = BBox.union_all(boxes)
        return bb if bb is not None else BBox(self._x, self._y, 0.0, 0.0)

    @property
    def bbox(self) -> BBox:
        self._apply_pending_rotate()
        if self._bbox_cache is None:
            self._bbox_cache = self.bbox_from_children()
        return self._bbox_cache

    @property
    def ink_bbox(self) -> BBox:
        boxes = [c.ink_bbox for c in self._children if c.visible]
        bb = BBox.union_all(boxes)
        return bb if bb is not None else self.bbox

    def _measure(self) -> None:
        pass

    def clip_bbox(self) -> BBox:
        """The rectangle ``clip=True`` clips to. Subclasses may narrow it."""
        return self.bbox

    def move(self, dx: float = 0.0, dy: float = 0.0) -> "Group":
        """Move every child (keeps the group's own transform clean)."""
        if dx == 0 and dy == 0:
            return self
        for c in self._children:
            c.move(dx, dy)
        self.invalidate()
        return self

    def resize(self, w: float = None, h: float = None, anchor: str = "nw"):
        """Scale the group's contents to a target size."""
        bb = self.bbox
        if bb.w <= 0 or bb.h <= 0:
            return self
        sx = 1.0 if w is None else float(w) / bb.w
        sy = 1.0 if h is None else float(h) / bb.h
        if w is not None and h is None:
            sy = sx
        if h is not None and w is None:
            sx = sy
        return self.scale_by(sx, sy, about=bb.anchor(anchor))

    def invalidate(self) -> "Group":
        self._bbox_cache = None
        return super().invalidate()

    # -- rendering -------------------------------------------------------
    def _render_content(self, ctx: RenderContext):
        kids = sorted([c for c in self._children if c.visible],
                      key=lambda c: (getattr(c, "z", 0) or 0))
        nodes = [c.render(ctx) for c in kids]
        nodes = [n for n in nodes if n is not None]
        if not nodes:
            return None
        g = Node("g")
        g.add(*nodes)
        if self.clip:
            bb = self.clip_bbox()
            clip_node = Node("clipPath").add(
                Node("rect", x=bb.x, y=bb.y, width=bb.w, height=bb.h))
            cid = ctx.add_def(clip_node)
            g.attrs["clip-path"] = f"url(#{cid})"
        return g

    def render(self, ctx: RenderContext) -> Node | None:
        if not self.visible:
            return None
        content = self._render_content(ctx)
        if content is None:
            return None
        attrs = self._wrapper_attrs(ctx)
        content.attrs.update(attrs)
        return content

    def __repr__(self) -> str:
        bb = self.bbox
        label = f" {self.name!r}" if self.name else ""
        return (f"<Group{label} {len(self._children)} children x={bb.x:.4g} "
                f"y={bb.y:.4g} w={bb.w:.4g} h={bb.h:.4g}>")
