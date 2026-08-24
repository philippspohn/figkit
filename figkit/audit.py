"""Static checks on a finished figure — the "did I make a mess?" pass.

The point of :func:`audit` is to answer, without rendering and looking, the
questions you would otherwise only notice by eye: is a label sticking out of
its box, is something covering something else, is that text invisible against
its background, does an arrow run straight through an unrelated box.

The hard part is *not* finding overlaps — it is not reporting the intentional
ones.  A figure is full of deliberate overlap: labels sit inside boxes, panels
sit behind their contents, arrows touch the things they connect, decorative
shapes fan across each other.  So the checks lean on structure rather than
guesswork:

* anything with ``z < 0`` is a declared backdrop and is expected to be under
  things;
* full containment is nesting, not collision;
* an element never collides with its own ancestors or descendants;
* line-like elements are tested by their actual path, never by the bounding
  box of a diagonal;
* a connector never collides with the elements it connects;
* by default only overlaps that can *hide content* are reported — two bare
  decorative polygons overlapping is your business, a box covering a label is
  a bug.

Every rule has an escape hatch: ``Element(audit=False)`` opts an element out
entirely, and each check can be switched off in the call.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .colors import luminance, parse_color
from .connectors import Connector
from .core import Element, Group
from .geom import BBox, Point
from .shapes import Line, Polyline, Shape
from .text import Text

__all__ = ["audit", "Finding", "Report", "paint_order"]

#: Elements whose geometry has no area, so a bounding box says little.
_LINE_LIKE = (Connector, Line)

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


# ==========================================================================
# Results
# ==========================================================================

@dataclass(frozen=True)
class Finding:
    """One thing that looks wrong."""

    kind: str
    message: str
    severity: str = "warning"
    where: Point | None = None
    elements: tuple = ()
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        at = f"  at ({self.where.x:.0f}, {self.where.y:.0f})" if self.where else ""
        return f"{self.kind:<10} {self.message}{at}"


class Report:
    """The result of an :func:`audit`. Falsy when the figure looks clean.

    >>> report = fig.audit()
    >>> print(report)
    >>> if report: ...
    """

    def __init__(self, findings=(), checked: int = 0):
        self.findings = sorted(
            findings, key=lambda f: (_SEVERITY_ORDER.get(f.severity, 3), f.kind))
        self.checked = checked

    def __bool__(self) -> bool:
        return bool(self.findings)

    def __len__(self) -> int:
        return len(self.findings)

    def __iter__(self):
        return iter(self.findings)

    def __getitem__(self, i):
        return self.findings[i]

    def by_kind(self, kind: str) -> list:
        return [f for f in self.findings if f.kind == kind]

    @property
    def errors(self) -> list:
        return [f for f in self.findings if f.severity == "error"]

    def raise_if_any(self) -> "Report":
        """Turn the report into an exception — handy in tests."""
        if self.findings:
            raise AssertionError(str(self))
        return self

    def summary(self) -> str:
        if not self.findings:
            return f"figkit audit: no issues ({self.checked} elements)"
        counts: dict = {}
        for f in self.findings:
            counts[f.kind] = counts.get(f.kind, 0) + 1
        parts = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        return (f"figkit audit: {len(self.findings)} issue"
                f"{'s' if len(self.findings) != 1 else ''} "
                f"({parts}) in {self.checked} elements")

    def __str__(self) -> str:
        if not self.findings:
            return self.summary()
        lines = [self.summary()]
        lines += [f"  {f}" for f in self.findings]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<Report {len(self.findings)} findings>"


# ==========================================================================
# Helpers
# ==========================================================================

def describe(el) -> str:
    """A short, recognisable name for an element."""
    kind = type(el).__name__
    if getattr(el, "name", None):
        return f"{kind}({el.name!r})"
    text = getattr(el, "text", None)
    if isinstance(text, str) and text.strip():
        flat = " ".join(text.split())
        if len(flat) > 24:
            flat = flat[:21] + "…"
        return f"{kind}({flat!r})"
    bb = el.bbox
    return f"{kind}@({bb.x:.0f},{bb.y:.0f})"


def paint_order(root) -> list:
    """Every element in the order it is painted (later = on top)."""
    out: list = []

    def walk(node):
        kids = getattr(node, "_children", None)
        if kids is None:
            out.append(node)
            label = _label_of(node)
            if label is not None and label is not node:
                out.append(label)      # a label paints right after its shape
            return
        out.append(node)
        for child in sorted([c for c in kids if c.visible],
                            key=lambda c: (getattr(c, "z", 0) or 0)):
            walk(child)

    for child in sorted([c for c in getattr(root, "_children", []) if c.visible],
                        key=lambda c: (getattr(c, "z", 0) or 0)):
        walk(child)
    return out


def _is_ancestor(a, b) -> bool:
    node = getattr(b, "parent", None)
    while node is not None:
        if node is a:
            return True
        node = getattr(node, "parent", None)
    return False


def _related(a, b) -> bool:
    return a is b or _is_ancestor(a, b) or _is_ancestor(b, a)


def _contains(outer: BBox, inner: BBox, tol: float = 0.5) -> bool:
    return (outer.x0 - tol <= inner.x0 and outer.y0 - tol <= inner.y0
            and outer.x1 + tol >= inner.x1 and outer.y1 + tol >= inner.y1)


def _label_of(el):
    """The text an element carries, if any."""
    if isinstance(el, Text):
        return el
    if isinstance(el, Shape):
        return el.label
    return None


def _carries_content(el) -> bool:
    """True when covering this element would hide something meaningful."""
    from .image import Image
    if isinstance(el, (Text, Image)):
        return True
    label = _label_of(el)
    return label is not None and bool(str(label.text).strip())


def _is_content(el) -> bool:
    """True when the element *is* the readable thing, not merely its container.

    A labelled box counts as content-bearing for routing purposes, but for
    overlap the label is audited as an item in its own right — so treating the
    box as content too would flag anything grazing its edge, far from any
    glyph.
    """
    from .image import Image
    return isinstance(el, (Text, Image))


def _endpoint_elements(conn: Connector, candidates=()) -> set:
    """Elements a connector legitimately touches: its endpoints and kin.

    Anchors and elements name their target directly. Raw coordinates do not,
    so an endpoint that lands inside an element counts as connecting to it —
    otherwise ``arrow((0, 9), (label.bbox.cx, label.bbox.cy))`` gets reported
    as passing through the very thing it points at.
    """
    out = set()
    for ref in (conn.start_ref, conn.end_ref, *conn.waypoints):
        el = getattr(ref, "element", None) or (ref if isinstance(ref, Element)
                                               else None)
        if el is None:
            continue
        for descendant in el.descendants():   # the endpoint and what it holds
            out.add(id(descendant))
        node = getattr(el, "parent", None)    # …and the groups holding it, but
        while node is not None:               # NOT their other children
            out.add(id(node))
            node = getattr(node, "parent", None)
    try:
        _d, start, _sd, end, _ed = conn.geometry()
    except Exception:
        return out
    for el in candidates:
        bb = el.bbox
        if bb.contains(start) or bb.contains(end):
            out.add(id(el))
    return out


def _segment_hits_rect(p: Point, q: Point, bb: BBox) -> bool:
    """Liang-Barsky: does segment p->q cross the interior of ``bb``?"""
    dx, dy = q.x - p.x, q.y - p.y
    t0, t1 = 0.0, 1.0
    for num, den in ((p.x - bb.x0, -dx), (bb.x1 - p.x, dx),
                     (p.y - bb.y0, -dy), (bb.y1 - p.y, dy)):
        if den == 0:
            if num < 0:
                return False
            continue
        t = num / den
        if den < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return t0 <= t1


def _polyline(el) -> list:
    """The drawn path of a line-like element, as points."""
    if isinstance(el, Connector):
        return el.polyline(20)
    if isinstance(el, Polyline):
        return list(el.points)
    return []


def _hits(el, bb: BBox) -> bool:
    """Does the element's actual ink reach into ``bb``?"""
    if isinstance(el, _LINE_LIKE) or (isinstance(el, Polyline) and not el.closed):
        pts = _polyline(el)
        return any(_segment_hits_rect(pts[i], pts[i + 1], bb)
                   for i in range(len(pts) - 1))
    return el.bbox.intersection(bb) is not None


def _solid_fill(el):
    """The element's fill colour, if it actually paints a solid area."""
    if isinstance(el, (Text, Connector)) or isinstance(el, Polyline) and not el.closed:
        return None
    fill = el.prop("fill", None)
    if fill in (None, "none") or isinstance(fill, dict):
        return None
    try:
        parsed = parse_color(fill)
    except ValueError:
        return None
    if parsed is None or parsed[3] < 0.55:
        return None
    opacity = el.prop("fill_opacity", None)
    if opacity is not None and float(opacity) < 0.55:
        return None
    return fill


# ==========================================================================
# The checks
# ==========================================================================

def audit(figure, *, overlap="content", overflow: bool = True,
          contrast: bool = True, crossing: bool = True,
          degenerate: bool = True, offscreen: bool = True,
          min_overlap: float = 4.0, min_contrast: float = 3.0,
          ignore=()) -> Report:
    """Check a figure for the mistakes you would otherwise spot by eye.

    ``overlap`` is ``"content"`` (default — only overlaps that can hide text or
    an image), ``"all"`` (any partial overlap between drawn elements) or
    ``False``.  ``ignore`` is a collection of elements to skip entirely.
    """
    skip = {id(e) for e in ignore}
    findings: list = []

    elements = [e for e in figure.descendants()
                if e is not figure and e.visible
                and getattr(e, "audit_enabled", True) and id(e) not in skip]
    leaves = [e for e in elements if not isinstance(e, Group)]
    # A shape's label is not in the element tree, but covering it is exactly
    # the bug we care most about — so audit it as an item in its own right.
    for shape in list(leaves):
        label = _label_of(shape)
        if label is not None and label is not shape \
                and str(label.text).strip() and getattr(shape, "audit_enabled", True):
            leaves.append(label)
    # Anything deliberately pushed behind is a backdrop; it is *supposed* to
    # sit under other things.
    foreground = [e for e in leaves if (getattr(e, "z", 0) or 0) >= 0]

    order = {id(el): i for i, el in enumerate(paint_order(figure))}
    if overlap:
        findings += _check_overlaps(foreground, min_overlap,
                                    content_only=(overlap != "all"),
                                    order=order)
    if crossing:
        findings += _check_crossings(figure, foreground)
    if overflow:
        findings += _check_overflow(elements)
    if contrast:
        findings += _check_contrast(figure, min_contrast)
    if degenerate:
        findings += _check_degenerate(leaves)
    if offscreen:
        findings += _check_offscreen(figure, leaves)

    return Report(_dedupe(findings), checked=len(elements))


def _owner(el):
    """A shape's label reports as the shape, so one problem yields one finding."""
    parent = getattr(el, "parent", None)
    if parent is not None and _label_of(parent) is el:
        return parent
    return el


def _dedupe(findings) -> list:
    """Collapse findings that describe the same problem via a label and its shape."""
    seen: dict = {}
    for f in findings:
        key = (f.kind, frozenset(id(_owner(e)) for e in f.elements))
        current = seen.get(key)
        if current is None or _SEVERITY_ORDER.get(f.severity, 3) < \
                _SEVERITY_ORDER.get(current.severity, 3):
            seen[key] = f
    return list(seen.values())


def _obscures(el) -> bool:
    """Would painting this element on top actually hide what is underneath?"""
    return _solid_fill(el) is not None or _carries_content(el)


def _check_overlaps(items, min_overlap: float, content_only: bool,
                    order: dict = None) -> list:
    order = order or {}
    out = []
    for i, a in enumerate(items):
        if isinstance(a, Connector):
            continue                       # handled by the crossing check
        abox = a.bbox
        for b in items[i + 1:]:
            if isinstance(b, Connector) or _related(a, b):
                continue
            bbox = b.bbox
            inter = abox.intersection(bbox)
            if inter is None:
                continue
            area = inter.w * inter.h
            if area < min_overlap:
                continue                   # touching edges is not a collision
            lower, upper = (a, b) if order.get(id(a), 0) <= order.get(id(b), 0) \
                else (b, a)
            if _contains(abox, bbox) or _contains(bbox, abox):
                # Nesting is normal — but only when the container is the one
                # underneath. A filled box painted *over* something it encloses
                # hides it completely, which is the worst case, not an exempt one.
                container = a if _contains(abox, bbox) else b
                inner = b if container is a else a
                if container is upper and _obscures(container) \
                        and _is_content(inner):
                    out.append(Finding(
                        "overlap",
                        f"{describe(container)} is painted over "
                        f"{describe(inner)}, hiding it completely",
                        severity="error", where=inter.center,
                        elements=(container, inner),
                        detail={"area": area, "hidden": 1.0}))
                continue
            hidden = (inter.w * inter.h) / max(1.0, lower.bbox.w * lower.bbox.h)
            if content_only:
                # Two ways an overlap is worth reporting:
                #  1. something readable is being covered up, at any size, or
                #  2. a large slice of an unrelated element is buried — which
                #     is what a mis-placed box looks like.
                # Shapes drawn together under one parent are exempt from (2):
                # a fan of wedges or a wireframe overlaps itself on purpose.
                covers_content = _is_content(lower) and _obscures(upper)
                buries = (hidden > 0.25 and _obscures(upper)
                          and a.parent is not b.parent)
                if not (covers_content or buries):
                    continue
            if not (_hits(a, inter) and _hits(b, inter)):
                continue                   # bounding boxes met, the ink did not
            out.append(Finding(
                "overlap",
                f"{describe(upper)} covers {describe(lower)} "
                f"({area:.0f}px², {hidden:.0%} of it)",
                severity="error" if hidden > 0.5 else "warning",
                where=inter.center, elements=(upper, lower),
                detail={"area": area, "hidden": hidden}))
    return out


def _check_crossings(figure, items) -> list:
    """Arrows running through elements they do not connect."""
    out = []
    connectors = [e for e in items if isinstance(e, Connector)]
    targets = [e for e in items
               if not isinstance(e, Connector) and _carries_content(e)]
    owners = {id(e) for e in targets}
    targets = [e for e in targets                 # a label and its shape are
               if id(_owner(e)) not in owners or _owner(e) is e]  # one target
    for conn in connectors:
        allowed = _endpoint_elements(conn, targets)
        # A perfectly horizontal or vertical connector has a zero-area bbox,
        # which would never "intersect" anything; pad it for the prefilter.
        cbox = conn.bbox.expand(1.0)
        pts = conn.polyline(24)
        if len(pts) < 2:
            continue
        for el in targets:
            if id(el) in allowed or _related(conn, el):
                continue
            bb = el.bbox
            if cbox.intersection(bb) is None:
                continue
            inner = bb.shrink(1.0)         # touching an edge is fine
            if inner.w <= 0 or inner.h <= 0:
                continue
            if any(_segment_hits_rect(pts[i], pts[i + 1], inner)
                   for i in range(len(pts) - 1)):
                out.append(Finding(
                    "crossing",
                    f"{describe(conn)} passes through {describe(el)}, "
                    f"which it does not connect",
                    severity="warning", where=bb.center, elements=(conn, el)))
    return out


def _check_overflow(elements, tolerance: float = 1.0) -> list:
    """Labels that stick out of the shape they belong to.

    Measured against the shape's own box rather than its padding box: padding
    is a layout hint, and optical centring deliberately lets a line box sit a
    hair outside it.  Text escaping the *shape* is the actual defect.
    """
    from .components import Panel
    out = []
    for el in elements:
        if not isinstance(el, Shape) or isinstance(el, Panel):
            continue          # a Panel places its label outside on purpose
        label = el.label
        if label is None or not str(label.text).strip():
            continue
        box = el.bbox
        lb = label.bbox
        # vertically, judge by the cap band: descender space below the last
        # baseline is empty, and counting it would flag every centred label
        band = label.optical_bbox
        dx = max(0.0, box.x0 - lb.x0) + max(0.0, lb.x1 - box.x1)
        dy = max(0.0, box.y0 - band.y0) + max(0.0, band.y1 - box.y1)
        if dx > tolerance or dy > tolerance:
            bits = []
            if dx > tolerance:
                bits.append(f"{dx:.0f}px horizontally")
            if dy > tolerance:
                bits.append(f"{dy:.0f}px vertically")
            out.append(Finding(
                "overflow",
                f"label of {describe(el)} sticks out of it by "
                f"{' and '.join(bits)}",
                severity="error", where=box.center, elements=(el,),
                detail={"dx": dx, "dy": dy}))
    return out


def _check_contrast(figure, min_contrast: float) -> list:
    """Text that will be hard or impossible to read on its backdrop."""
    out = []
    order = paint_order(figure)
    index = {id(el): i for i, el in enumerate(order)}
    painters = [(i, el) for i, el in enumerate(order) if _solid_fill(el)]
    page = figure.background or figure.prop("background", "#ffffff") or "#ffffff"

    for el in order:
        label = _label_of(el)
        if label is None or not str(label.text).strip():
            continue
        if not getattr(el, "audit_enabled", True):
            continue
        colours = [label.text_color()]
        try:
            colours.extend(label._resolve_value(run.color)
                           for line in label.layout.lines for run in line.runs
                           if run.color is not None)
        except Exception:
            pass
        unique = []
        for candidate in colours:
            if candidate is not None and candidate not in unique:
                unique.append(candidate)
        colours = unique
        if not colours:
            continue
        lb = label.bbox
        pos = index.get(id(el), 0)
        backdrop = page
        for i, other in painters:
            if i > pos:
                continue
            # `other is el` is deliberately allowed: a box's label sits on that
            # box's own fill, which is the commonest backdrop of all.
            if _contains(other.bbox, lb, tol=-0.5):
                backdrop = _solid_fill(other)
        for colour in colours:
            try:
                ratio = _contrast_ratio(colour, backdrop)
            except (TypeError, ValueError):
                continue
            if ratio < min_contrast - 1e-9:
                out.append(Finding(
                    "contrast",
                    f"{describe(el)}: text {colour} on {backdrop} has contrast "
                    f"{_floor2(ratio)}:1 (want {min_contrast:.2f}:1)",
                    severity="error" if ratio < 1.6 else "warning",
                    where=lb.center, elements=(el,),
                    detail={"ratio": ratio, "color": colour,
                            "background": backdrop}))
    return out


def _floor2(value: float) -> str:
    """Round *down* to 2dp, so a failing ratio never prints as the threshold."""
    return f"{math.floor(value * 100) / 100:.2f}"


def _contrast_ratio(fg, bg) -> float:
    lf, lb = luminance(fg), luminance(bg)
    hi, lo = max(lf, lb), min(lf, lb)
    return (hi + 0.05) / (lo + 0.05)


def _check_degenerate(leaves) -> list:
    """Zero-size shapes and zero-length arrows: almost always a mistake."""
    out = []
    for el in leaves:
        if isinstance(el, Connector):
            if el.length < 1.0:
                out.append(Finding(
                    "degenerate", f"{describe(el)} is {el.length:.2f}px long",
                    severity="error", where=el.bbox.center, elements=(el,)))
            continue
        if isinstance(el, (Line, Polyline)):
            continue                        # a horizontal line has zero height
        bb = el.bbox
        if bb.w <= 0 or bb.h <= 0:
            out.append(Finding(
                "degenerate", f"{describe(el)} has zero size "
                              f"({bb.w:.0f}x{bb.h:.0f})",
                severity="error", where=bb.center, elements=(el,)))
    return out


def _check_offscreen(figure, leaves) -> list:
    """Content outside a pinned viewbox. Auto-sized figures cannot have any."""
    if figure._viewbox is None and figure._fixed_w is None \
            and figure._fixed_h is None:
        return []
    view = figure.viewbox()
    out = []
    for el in leaves:
        bb = el.ink_bbox
        if view.intersection(bb) is None:
            out.append(Finding(
                "offscreen", f"{describe(el)} lies entirely outside the canvas",
                severity="error", where=bb.center, elements=(el,)))
        elif not _contains(view, bb):
            out.append(Finding(
                "offscreen", f"{describe(el)} is clipped by the canvas edge",
                severity="warning", where=bb.center, elements=(el,)))
    return out
