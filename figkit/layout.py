"""Arrangement helpers: align, distribute, stack, grid and fit.

Nothing here is automatic layout — every function positions elements once,
when you call it, and then gets out of the way.
"""

from __future__ import annotations

import math

from .components import Panel
from .core import Element, Group
from .geom import BBox, Point, to_point
from .style import enum_value

__all__ = [
    "align", "align_h", "align_v", "distribute_h", "distribute_v",
    "spread_h", "spread_v", "hstack", "vstack", "grid", "fit", "frame_around",
    "between", "midpoint", "center_on", "group", "bbox_of", "circular",
    "same_width", "same_height", "same_size", "shift", "baseline_of",
    "brace_around",
]

_EDGE_AXIS = {
    "left": "x", "w": "x", "right": "x", "e": "x",
    "center_x": "x", "cx": "x", "middle_x": "x",
    "top": "y", "n": "y", "bottom": "y", "s": "y",
    "center_y": "y", "cy": "y", "middle_y": "y",
}


def bbox_of(items) -> BBox:
    """Union bbox of a list of elements/anchors/points."""
    boxes = []
    for it in _iter(items):
        bb = getattr(it, "bbox", None)
        if isinstance(bb, BBox):
            boxes.append(bb)
        else:
            p = to_point(it)
            boxes.append(BBox(p.x, p.y, 0, 0))
    return BBox.union_all(boxes) or BBox(0, 0, 0, 0)


def _iter(items):
    if items is None:
        return []
    if isinstance(items, (list, tuple, set)):
        out = []
        for i in items:
            out.extend(_iter(i))
        return out
    if isinstance(items, Group) and not isinstance(items, Element):
        return list(items)
    return [items]


# ==========================================================================
# Alignment
# ==========================================================================

def align(items, edge: str = "top", to=None) -> list:
    """Line elements up on one edge (or centre axis).

    ``edge`` is one of ``top/bottom/left/right/center_x/center_y/center``.
    ``to`` is the reference (an element, point or bbox); defaults to the first
    item.

    >>> align([a, b, c], "top")
    >>> align([a, b], "center_x", to=title)
    """
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if not els:
        return els
    e = str(edge).lower()
    ref = els[0] if to is None else to
    ref_bb = ref if isinstance(ref, BBox) else bbox_of(ref)
    if e in ("center", "middle"):
        for el in els:
            el.move(ref_bb.cx - el.bbox.cx, ref_bb.cy - el.bbox.cy)
        return els
    if e not in _EDGE_AXIS:
        raise ValueError(f"align edge={edge!r}; use one of "
                         f"{sorted(set(_EDGE_AXIS) | {'center'})}")
    for el in els:
        bb = el.bbox
        if e in ("left", "w"):
            el.move(ref_bb.x0 - bb.x0, 0)
        elif e in ("right", "e"):
            el.move(ref_bb.x1 - bb.x1, 0)
        elif e in ("center_x", "cx", "middle_x"):
            el.move(ref_bb.cx - bb.cx, 0)
        elif e in ("top", "n"):
            el.move(0, ref_bb.y0 - bb.y0)
        elif e in ("bottom", "s"):
            el.move(0, ref_bb.y1 - bb.y1)
        else:
            el.move(0, ref_bb.cy - bb.cy)
    return els


def align_h(items, edge: str = "center_y", to=None) -> list:
    """Align on a horizontal line (i.e. equalise ``y``)."""
    return align(items, edge, to)


def align_v(items, edge: str = "center_x", to=None) -> list:
    """Align on a vertical line (i.e. equalise ``x``)."""
    return align(items, edge, to)


# ==========================================================================
# Distribution
# ==========================================================================

def distribute_h(items, gap: float = 20.0, start=None, align_edge=None) -> list:
    """Lay items out left-to-right with a fixed ``gap`` between them.

    Keeps the first item where it is unless ``start`` (an x coordinate) is given.

    >>> distribute_h([a, b, c], gap=24)
    """
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if not els:
        return els
    x = els[0].bbox.x0 if start is None else float(start)
    for el in els:
        el.move(x - el.bbox.x0, 0)
        x = el.bbox.x1 + gap
    if align_edge:
        align(els, align_edge, to=els[0])
    return els


def distribute_v(items, gap: float = 20.0, start=None, align_edge=None) -> list:
    """Lay items out top-to-bottom with a fixed ``gap``."""
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if not els:
        return els
    y = els[0].bbox.y0 if start is None else float(start)
    for el in els:
        el.move(0, y - el.bbox.y0)
        y = el.bbox.y1 + gap
    if align_edge:
        align(els, align_edge, to=els[0])
    return els


def spread_h(items, x0=None, x1=None, mode: str = "edges") -> list:
    """Spread items evenly across a horizontal span.

    ``mode="edges"`` gives equal gaps between bounding boxes;
    ``mode="centers"`` spaces the centres evenly (good for equal-width items).
    """
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if len(els) < 2:
        return els
    els.sort(key=lambda e: e.bbox.cx)
    lo = els[0].bbox.x0 if x0 is None else _coord(x0, "x")
    hi = els[-1].bbox.x1 if x1 is None else _coord(x1, "x")
    if mode == "centers":
        c0 = els[0].bbox.cx if x0 is None else lo
        c1 = els[-1].bbox.cx if x1 is None else hi
        step = (c1 - c0) / (len(els) - 1)
        for i, el in enumerate(els):
            el.move(c0 + i * step - el.bbox.cx, 0)
        return els
    total_w = sum(e.bbox.w for e in els)
    gap = ((hi - lo) - total_w) / (len(els) - 1)
    x = lo
    for el in els:
        el.move(x - el.bbox.x0, 0)
        x = el.bbox.x1 + gap
    return els


def spread_v(items, y0=None, y1=None, mode: str = "edges") -> list:
    """Spread items evenly across a vertical span."""
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if len(els) < 2:
        return els
    els.sort(key=lambda e: e.bbox.cy)
    lo = els[0].bbox.y0 if y0 is None else _coord(y0, "y")
    hi = els[-1].bbox.y1 if y1 is None else _coord(y1, "y")
    if mode == "centers":
        c0 = els[0].bbox.cy if y0 is None else lo
        c1 = els[-1].bbox.cy if y1 is None else hi
        step = (c1 - c0) / (len(els) - 1)
        for i, el in enumerate(els):
            el.move(0, c0 + i * step - el.bbox.cy)
        return els
    total_h = sum(e.bbox.h for e in els)
    gap = ((hi - lo) - total_h) / (len(els) - 1)
    y = lo
    for el in els:
        el.move(0, y - el.bbox.y0)
        y = el.bbox.y1 + gap
    return els


def _coord(value, axis: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    p = to_point(value)
    return p.x if axis == "x" else p.y


# ==========================================================================
# Stacks & grids
# ==========================================================================

def hstack(items, gap: float = 16.0, align: str = "center", at=None,
           pad=None, panel=False, name: str = None, **panel_style) -> Group:
    """Place items in a row and return them as a movable :class:`Group`.

    ``align`` is ``center`` / ``top`` / ``bottom``, or ``"baseline"`` to set
    the items like an equation: text baselines line up, and items without text
    (a matrix, an image) centre on the maths axis.

    >>> row = hstack([a, b, c], gap=20, align="top")
    >>> row.right_of(title, gap=30)
    >>> formula = hstack([Text("$C =$"), matrix, Text("$\\phi$")],
    ...                  gap=8, align="baseline")
    """
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if not els:
        return Group(name=name)
    distribute_h(els, gap=gap)
    _align_cross(els, align, horizontal=True)
    if panel or pad is not None or panel_style:
        result = fit(els, pad=16 if pad is None else pad, name=name,
                     **panel_style)
    else:
        result = Group(*els, name=name)
    if at is not None:
        p = to_point(at)
        result.at(p.x, p.y, anchor="nw")
    return result


def vstack(items, gap: float = 12.0, align: str = "center", at=None,
           pad=None, panel=False, name: str = None, **panel_style) -> Group:
    """Place items in a column and return them as a movable :class:`Group`."""
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if not els:
        return Group(name=name)
    distribute_v(els, gap=gap)
    _align_cross(els, align, horizontal=False)
    if panel or pad is not None or panel_style:
        result = fit(els, pad=16 if pad is None else pad, name=name,
                     **panel_style)
    else:
        result = Group(*els, name=name)
    if at is not None:
        p = to_point(at)
        result.at(p.x, p.y, anchor="nw")
    return result


def baseline_of(element) -> float:
    """The first text baseline inside ``element``, or ``None`` if it has none.

    Looks through shapes to their labels and through groups to their first
    baselined descendant, so a box, a bare label and a component all answer.
    """
    from .text import Text
    if isinstance(element, Text):
        return element.first_baseline
    label = getattr(element, "label", None)
    if isinstance(label, Text):
        return label.first_baseline
    for child in getattr(element, "_children", ()):
        found = baseline_of(child)
        if found is not None:
            return found
    return None


def _math_axis(element, baseline: float) -> float:
    """Half an x-height above the baseline — where a formula's centre sits."""
    from .fonts import get_font
    from .text import Text
    ref = element if isinstance(element, Text) else getattr(element, "label", None)
    if ref is None:
        return baseline
    size = float(ref.prop("font_size", 14) or 14)
    metrics = get_font(ref.prop("font_family"), ref.prop("font_weight"),
                       ref.prop("font_style")).metrics
    return baseline - (metrics.x_height or 0.5) * size / 2.0


def _align_baselines(els) -> None:
    """Line items up on their text baseline, as an equation would be set.

    Items with no text of their own (a matrix, an image) are centred on the
    maths axis instead, which is what reads correctly beside a symbol.
    """
    found = [(el, baseline_of(el)) for el in els]
    reference = next(((el, b) for el, b in found if b is not None), None)
    if reference is None:
        ref_box = bbox_of(els)
        for el in els:
            el.move(0, ref_box.cy - el.bbox.cy)
        return
    ref_el, ref_baseline = reference
    axis = _math_axis(ref_el, ref_baseline)
    for el, baseline in found:
        if baseline is not None:
            el.move(0, ref_baseline - baseline)
        else:
            el.move(0, axis - el.bbox.cy)


def _align_cross(els, how: str, horizontal: bool) -> None:
    if not how or str(how).lower() in ("none", "keep"):
        return
    a = str(how).lower()
    if horizontal and a == "baseline":
        _align_baselines(els)
        return
    if horizontal:
        edge = {"top": "top", "n": "top", "bottom": "bottom", "s": "bottom",
                "center": "center_y", "middle": "center_y"}.get(a)
    else:
        edge = {"left": "left", "w": "left", "right": "right", "e": "right",
                "center": "center_x", "middle": "center_x"}.get(a)
    if edge is None:
        raise ValueError(f"align={how!r} is not valid for this stack")
    ref = bbox_of(els)
    align(els, edge, to=ref)


def grid(items, cols: int = None, rows: int = None, gap=16, at=None,
         align: str = "center", equal: bool = True, name: str = None,
         order: str = "row") -> Group:
    """Arrange items in a grid and return a :class:`Group`.

    ``gap`` is a scalar or ``(gap_x, gap_y)``. With ``equal=True`` every cell
    is the size of the largest item, so columns line up.
    """
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if not els:
        return Group(name=name)
    align = enum_value(align, "align", {
        value: value for value in
        ("center", "left", "right", "top", "bottom", "nw", "ne", "sw", "se")
    })
    order = enum_value(order, "order", {
        "row": "row", "rows": "row", "row-major": "row",
        "col": "col", "cols": "col", "column": "col",
        "columns": "col", "column-major": "col",
    })
    n = len(els)
    if cols is None and rows is None:
        cols = math.ceil(math.sqrt(n))
    if cols is None:
        cols = math.ceil(n / rows)
    rows = rows or math.ceil(n / cols)
    gx, gy = (gap if isinstance(gap, (tuple, list)) else (gap, gap))
    origin = to_point(at) if at is not None else bbox_of(els).anchor("nw")

    if equal:
        cw = max(e.bbox.w for e in els)
        ch = max(e.bbox.h for e in els)
        col_w = [cw] * cols
        row_h = [ch] * rows
    else:
        col_w = [0.0] * cols
        row_h = [0.0] * rows
        for idx, el in enumerate(els):
            r, c = _rc(idx, cols, rows, order)
            col_w[c] = max(col_w[c], el.bbox.w)
            row_h[r] = max(row_h[r], el.bbox.h)

    xs = [origin.x]
    for w in col_w[:-1]:
        xs.append(xs[-1] + w + gx)
    ys = [origin.y]
    for h in row_h[:-1]:
        ys.append(ys[-1] + h + gy)

    for idx, el in enumerate(els):
        r, c = _rc(idx, cols, rows, order)
        cell = BBox(xs[c], ys[r], col_w[c], row_h[r])
        anchor = {"center": "center", "left": "w", "right": "e",
                  "top": "n", "bottom": "s", "nw": "nw", "ne": "ne",
                  "sw": "sw", "se": "se"}[align]
        target = cell.anchor(anchor)
        el.at(target.x, target.y, anchor=anchor)
    return Group(*els, name=name)


def _rc(idx: int, cols: int, rows: int, order: str) -> tuple:
    if order == "col":
        return idx % rows, idx // rows
    return idx // cols, idx % cols


# ==========================================================================
# Containers
# ==========================================================================

def fit(*items, pad=16, label=None, label_pos: str = "above_left",
        name: str = None, style=None, **panel_style) -> Group:
    """Wrap elements in a container box sized around them.

    Returns a :class:`Group` holding the panel (behind) plus the items, so the
    whole thing moves as a unit.  ``result.panel`` is the box itself.

    ``label_pos`` defaults to ``"above_left"`` (outside the box, where it
    cannot collide with the contents); ``"nw"``, ``"n"``, ``"below"`` and the
    other anchors also work.

    >>> frame = fit(ipm, cmn, pad=20, label="Fused operation", dash=True)
    >>> frame.below_of(header, gap=24)
    """
    els = [e for e in _iter(items) if isinstance(e, Element)]
    panel = Panel(els, pad=pad, label=label, label_pos=label_pos,
                  style=style, add=False, **panel_style)
    g = Group(panel, *els, name=name)
    g.panel = panel
    return g


def frame_around(items, pad=16, **style) -> Panel:
    """Just the container box (no group), tracking ``items`` as they move."""
    els = [e for e in _iter(items) if isinstance(e, Element)]
    return Panel(els, pad=pad, **style)


def brace_around(items, side: str = "top", gap: float = 8.0,
                 depth: float = 10.0, label=None, pad: float = 0.0,
                 **kw):
    """A :class:`~figkit.components.Brace` spanning a set of elements.

    >>> brace_around([a, b, c], side="top", label="encoder")
    """
    from .components import Brace
    box = bbox_of(items).expand(pad)
    s = str(side).lower()
    if s in ("top", "n", "above"):
        start, end = (box.x0, box.y0 - gap), (box.x1, box.y0 - gap)
        facing = "up"
    elif s in ("bottom", "s", "below"):
        start, end = (box.x1, box.y1 + gap), (box.x0, box.y1 + gap)
        facing = "down"
    elif s in ("left", "w"):
        start, end = (box.x0 - gap, box.y0), (box.x0 - gap, box.y1)
        facing = "left"
    elif s in ("right", "e"):
        start, end = (box.x1 + gap, box.y1), (box.x1 + gap, box.y0)
        facing = "right"
    else:
        raise ValueError(f"side={side!r}; use top/bottom/left/right")
    return Brace(start, end, depth=depth, side=facing, label=label, **kw)


def group(*items, name: str = None, **kw) -> Group:
    """Bundle elements into a :class:`Group`."""
    return Group(*[e for e in _iter(items)], name=name, **kw)


# ==========================================================================
# Point helpers
# ==========================================================================

def between(a, b, t: float = 0.5) -> Point:
    """The point ``t`` of the way from ``a`` to ``b`` (centres by default).

    >>> mid = between(fm, fn)          # vertically between two boxes
    >>> arrow(solver.e, mid)
    """
    return to_point(a).lerp(to_point(b), t)


midpoint = between


def center_on(el: Element, target, axis: str = "both") -> Element:
    """Centre ``el`` on ``target`` (an element, anchor or point)."""
    bb = bbox_of(target)
    a = str(axis).lower()
    if a in ("both", "xy"):
        return el.center_at(bb.cx, bb.cy)
    if a == "x":
        return el.move(bb.cx - el.bbox.cx, 0)
    if a == "y":
        return el.move(0, bb.cy - el.bbox.cy)
    raise ValueError(f"axis={axis!r}; use both/x/y")


def circular(items, center=(0, 0), radius: float = 120.0,
             start_angle: float = -90.0, sweep: float = 360.0,
             rotate_items: bool = False) -> list:
    """Place items evenly around a circle (cycle diagrams)."""
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if not els:
        return els
    c = to_point(center)
    n = len(els)
    step = sweep / n if abs(sweep) >= 359.99 else sweep / max(1, n - 1)
    for i, el in enumerate(els):
        a = math.radians(start_angle + i * step)
        el.center_at(c.x + math.cos(a) * radius, c.y + math.sin(a) * radius)
        if rotate_items:
            el.rotate(start_angle + i * step + 90)
    return els


def shift(items, dx: float = 0.0, dy: float = 0.0) -> list:
    """Move several elements at once."""
    els = [e for e in _iter(items) if isinstance(e, Element)]
    for el in els:
        el.move(dx, dy)
    return els


def same_width(items, width: float = None, anchor: str = "center") -> list:
    """Give every item the same width (the widest, unless ``width`` is given)."""
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if not els:
        return els
    w = width if width is not None else max(e.bbox.w for e in els)
    for el in els:
        el.resize(w=w, anchor=anchor)
    return els


def same_height(items, height: float = None, anchor: str = "center") -> list:
    """Give every item the same height (the tallest, unless given)."""
    els = [e for e in _iter(items) if isinstance(e, Element)]
    if not els:
        return els
    h = height if height is not None else max(e.bbox.h for e in els)
    for el in els:
        el.resize(h=h, anchor=anchor)
    return els


def same_size(items, anchor: str = "center") -> list:
    """Give every item the same width *and* height."""
    same_width(items, anchor=anchor)
    return same_height(items, anchor=anchor)
