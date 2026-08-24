"""Higher-level building blocks: panels, matrices, braces, legends, tables."""

from __future__ import annotations

import math

from .colors import colormap, contrast_color, to_hex
from .component import Component
from .core import Element, Group
from .style import Style, enum_value
from .geom import BBox, Point, _expand_spec, to_point
from .paint import paint_attrs
from .shapes import Box, Marker
from .svgdoc import Node, RenderContext
from .svgpath import fmt
from .text import Text

_GROUP_KEYS = frozenset({"name", "z", "visible", "opacity", "transform",
                         "clip", "add", "theme", "style"})

__all__ = ["Panel", "Matrix", "Vector", "Heatmap", "Brace", "Bracket",
           "Legend", "Table", "Callout", "Spacer", "ColorBar",
           "LabelledMatrix"]


# ==========================================================================
# Panel — a box that tracks a set of elements
# ==========================================================================

class Panel(Box):
    """A rectangle sized around other elements, drawn behind them.

    Created by :func:`figkit.layout.fit`, but usable directly:

    >>> Panel([box_a, box_b], pad=16, label="Fused operation", dash=True)
    """

    role = "panel"
    default_padding = 0

    def __init__(self, targets=None, pad=16, label=None,
                 label_pos: str = "above_left",
                 label_gap: float = 6.0, label_style=None, follow: bool = True,
                 **kw):
        if targets is None:
            targets = []
        elif isinstance(targets, Element):
            targets = [targets]
        self.targets = list(targets)
        self.pad = _expand_spec(pad)
        self.follow = follow
        self.label_pos = str(label_pos).lower()
        self.label_gap = float(label_gap)
        kw.setdefault("z", -1000)
        kw.pop("text", None)
        super().__init__(None, **kw)
        self._panel_label: Text | None = None
        if label:
            self._panel_label = Text(label, add=False, style=label_style)
            self._panel_label.parent = self
            self._panel_label.role = "label"
        self.invalidate()

    def add_target(self, *elements) -> "Panel":
        for el in elements:
            if el is not None and el is not self:
                self.targets.append(el)
        return self.invalidate()

    def _measure(self) -> None:
        if self.follow and self.targets:
            self._dirty = False
            bb = BBox.union_all([t.ink_bbox for t in self.targets
                                 if t.visible and t is not self])
            if bb is not None:
                t, r, b, l = self.pad
                bb = bb.expand(0, top=t, right=r, bottom=b, left=l)
                inv = self.world_matrix()
                if not inv.is_identity:
                    bb = inv.inverse().apply_bbox(bb)
                self._x, self._y, self._w, self._h = bb.x, bb.y, bb.w, bb.h
        else:
            super()._measure()
        if self._panel_label is not None:
            self._place_panel_label()

    @property
    def local_bbox(self) -> BBox:
        if self.follow and self.targets:
            self._dirty = True      # the elements we track may have moved
        self._ensure()
        return BBox(self._x, self._y, self._w or 0.0, self._h or 0.0)

    def _place_panel_label(self) -> None:
        lbl = self._panel_label
        bb = BBox(self._x, self._y, self._w or 0, self._h or 0)
        g = self.label_gap
        pos = self.label_pos
        inner = {"nw": ("nw", g, g), "n": ("n", 0, g), "ne": ("ne", -g, g),
                 "sw": ("sw", g, -g), "s": ("s", 0, -g), "se": ("se", -g, -g),
                 "w": ("w", g, 0), "e": ("e", -g, 0), "center": ("center", 0, 0)}
        if pos in inner:
            anchor, dx, dy = inner[pos]
            p = bb.anchor(anchor)
            lbl.place_local(p.x + dx, p.y + dy, anchor=anchor)
            return
        outer = {"above": ("s", "n", 0, -g), "top": ("s", "n", 0, -g),
                 "below": ("n", "s", 0, g), "bottom": ("n", "s", 0, g),
                 "left": ("e", "w", -g, 0), "right": ("w", "e", g, 0),
                 "above_left": ("sw", "nw", 0, -g),
                 "above_right": ("se", "ne", 0, -g)}
        anchor, side, dx, dy = outer.get(pos, ("s", "n", 0, -g))
        p = bb.anchor(side)
        lbl.place_local(p.x + dx, p.y + dy, anchor=anchor)

    @property
    def label(self) -> Text | None:
        self._ensure()
        return self._panel_label

    def _render_content(self, ctx: RenderContext):
        self._ensure()
        nodes = list(self.shape_nodes(ctx, self.local_bbox) or [])
        if self._panel_label is not None:
            n = self._panel_label.render(ctx)
            if n is not None:
                nodes.append(n)
        return nodes or None

    @property
    def ink_bbox(self) -> BBox:
        bb = super().ink_bbox
        if self._panel_label is not None:
            bb = bb.union(self._panel_label.ink_bbox)
        return bb


# ==========================================================================
# Matrix / heatmap
# ==========================================================================

class Matrix(Group):
    """A grid of coloured cells — feature vectors, attention maps, matrices.

    >>> Matrix([[0.1, 0.9], [0.5, 0.2]], cell=18, cmap="viridis")
    >>> Matrix(colors=[["#eee", "#333"]], cell=14)

    ``m.cell(i, j)`` returns the cell as a real element, so you can point an
    arrow at it or restyle it.
    """

    role = "matrix"

    def __init__(self, values=None, *, colors=None, rows: int = None,
                 cols: int = None, cell=16, gap: float = 0.0,
                 cmap="viridis", vmin: float = None, vmax: float = None,
                 radius: float = None, show_values: bool = False,
                 value_fmt="{:.2f}", value_color=None, value_size: float = None,
                 border=None, cell_style=None, x: float = 0.0, y: float = 0.0,
                 **kw):
        self._grid_values = _as_grid(values, rows, cols)
        self._grid_colors = _as_grid(colors, rows, cols) if colors else None
        if self._grid_values is None and self._grid_colors is None:
            self._grid_values = [[0.0] * (cols or 1) for _ in range(rows or 1)]
        src = self._grid_colors or self._grid_values
        self.n_rows = len(src)
        self.n_cols = max(len(r) for r in src) if src else 0
        cw, ch = (cell if isinstance(cell, (tuple, list)) else (cell, cell))
        self.cell_w, self.cell_h = float(cw), float(ch)
        self.gap = float(gap)
        self.cmap = cmap
        self._cells: list = []
        self._value_labels: list = []
        self._value_label_map: dict = {}
        # Paint properties passed to Matrix(...) style the *cells*, which is
        # what people mean by `Matrix(vals, stroke="#333")`.
        group_kw = {k: v for k, v in kw.items() if k in _GROUP_KEYS}
        cell_kw = {k: v for k, v in kw.items() if k not in _GROUP_KEYS}
        cell_style = Style(cell_style, **cell_kw) if cell_kw else cell_style
        super().__init__(**group_kw)

        flat = [v for row in (self._grid_values or []) for v in row
                if v is not None]
        lo = min(flat) if (flat and vmin is None) else vmin
        hi = max(flat) if (flat and vmax is None) else vmax
        self.vmin, self.vmax = lo, hi

        for i in range(self.n_rows):
            row_cells = []
            for j in range(self.n_cols):
                cx = x + j * (self.cell_w + self.gap)
                cy = y + i * (self.cell_h + self.gap)
                fill = self._cell_color(i, j)
                cell_el = Box(None, cx, cy, self.cell_w, self.cell_h,
                              style=cell_style, fill=fill, padding=0,
                              radius=radius if radius is not None else None,
                              add=False)
                cell_el.role = "matrix"
                self.add(cell_el)
                row_cells.append(cell_el)
                if show_values and self._grid_values:
                    v = self._value(i, j)
                    if v is None:
                        continue
                    txt = value_fmt.format(v) if not callable(value_fmt) \
                        else value_fmt(v)
                    col = value_color or contrast_color(fill)
                    lbl = Text(txt, add=False, color=col,
                               font_size=value_size or max(7.0, self.cell_h * 0.38))
                    lbl.parent = self
                    lbl.role = "label"
                    self.add(lbl)
                    lbl.center_at(cell_el.bbox.cx, cell_el.bbox.cy)
                    self._value_labels.append(lbl)
                    self._value_label_map[(i, j)] = lbl
            self._cells.append(row_cells)

        if border:
            bb = self.bbox
            frame = Box(None, bb.x, bb.y, bb.w, bb.h, fill="none",
                        stroke=border if isinstance(border, str) else "#333",
                        padding=0, radius=0, z=10, add=False)
            self.add(frame)
            self.border = frame

    # -- data ------------------------------------------------------------
    def _value(self, i: int, j: int):
        if not self._grid_values:
            return None
        row = self._grid_values[i] if i < len(self._grid_values) else []
        return row[j] if j < len(row) else None

    def _cell_color(self, i: int, j: int) -> str:
        if self._grid_colors:
            row = self._grid_colors[i] if i < len(self._grid_colors) else []
            if j < len(row) and row[j] is not None:
                return to_hex(row[j])
        v = self._value(i, j)
        if v is None:
            return "#dddddd"
        lo, hi = self.vmin, self.vmax
        t = 0.5 if (lo is None or hi is None or hi == lo) else (v - lo) / (hi - lo)
        return colormap(self.cmap, t)

    # -- access ----------------------------------------------------------
    def cell(self, i: int, j: int = 0) -> Box:
        """The cell element at row ``i``, column ``j`` (negatives wrap)."""
        return self._cells[i][j]

    @property
    def cells(self) -> list:
        return self._cells

    def row(self, i: int) -> list:
        return list(self._cells[i])

    def col(self, j: int) -> list:
        return [r[j] for r in self._cells]

    def shape(self) -> tuple:
        return (self.n_rows, self.n_cols)

    def highlight(self, i: int, j: int = 0, **style) -> Box:
        """Restyle one cell (e.g. ``highlight(0, 2, stroke='red', lw=2)``)."""
        c = self.cell(i, j)
        c.restyle(**style)
        c.to_front()
        label = self._value_label_map.get((i % self.n_rows, j % self.n_cols))
        if label is not None:
            label.to_front()
        return c


def Vector(values=None, *, orient: str = "v", **kw) -> Matrix:
    """A 1-D :class:`Matrix` — the little feature-vector strips in ML figures."""
    if values is None:
        values = []
    flat = list(values)
    orient = enum_value(orient, "orient", {
        "v": "v", "vertical": "v", "h": "h", "horizontal": "h",
    })
    if orient == "v":
        grid = [[v] for v in flat]
    else:
        grid = [flat]
    colors = kw.pop("colors", None)
    if colors is not None:
        colors = [[c] for c in colors] if orient == "v" \
            else [list(colors)]
        return Matrix(None, colors=colors, **kw)
    return Matrix(grid, **kw)


Heatmap = Matrix


class ColorBar(Group):
    """A gradient strip with min/max labels, for heatmap legends."""

    role = "group"

    def __init__(self, cmap="viridis", vmin=0.0, vmax=1.0, *, w: float = 14.0,
                 h: float = 120.0, steps: int = 24, orient: str = "v",
                 labels=True, label_fmt="{:.2g}", x: float = 0.0,
                 y: float = 0.0, **kw):
        super().__init__(**kw)
        orient = enum_value(orient, "orient", {
            "v": "v", "vertical": "v", "h": "h", "horizontal": "h",
        })
        vertical = orient == "v"
        n = max(2, int(steps))
        for i in range(n):
            t = i / (n - 1)
            pos = i / n
            span = (1.0 - pos) if i == n - 1 else (1.0 / n + 0.001)
            col = colormap(cmap, 1.0 - t if vertical else t)
            if vertical:
                seg = Box(None, x, y + pos * h, w, span * h, fill=col,
                          stroke="none", padding=0, radius=0, add=False)
            else:
                seg = Box(None, x + pos * w, y, span * w, h, fill=col,
                          stroke="none", padding=0, radius=0, add=False)
            self.add(seg)
        frame = Box(None, x, y, w, h, fill="none", stroke="#6b7280",
                    stroke_width=0.8, padding=0, radius=0, add=False)
        self.add(frame)
        if labels:
            lo = Text(label_fmt.format(vmin), add=False, font_size=10)
            hi = Text(label_fmt.format(vmax), add=False, font_size=10)
            self.add(lo, hi)
            if vertical:
                hi.at(x + w + 5, y, anchor="w")
                lo.at(x + w + 5, y + h, anchor="w")
            else:
                lo.at(x, y + h + 4, anchor="n")
                hi.at(x + w, y + h + 4, anchor="n")


# ==========================================================================
# Braces & brackets
# ==========================================================================

class Brace(Element):
    """A curly brace spanning two points, optionally labelled.

    >>> Brace(box_a.nw, box_c.ne, depth=12, label="encoder")
    """

    role = "brace"
    STROKE_WIDTH_ALIAS = True

    def __init__(self, start, end, *, depth: float = 12.0, side: str = "auto",
                 label=None, label_gap: float = 6.0, label_style=None,
                 sharpness: float = 0.55, **kw):
        self.start_ref = start
        self.end_ref = end
        self.depth = float(depth)
        self.side = str(side).lower()
        self.sharpness = float(sharpness)
        self.label_gap = float(label_gap)
        self._label: Text | None = None
        super().__init__(0, 0, None, None, **kw)
        if label:
            self._label = Text(label, add=False, style=label_style)
            self._label.parent = self
            self._label.role = "label"

    def _normal(self, p0: Point, p1: Point) -> Point:
        v = (p1 - p0).normalized()
        n = Point(-v.y, v.x)
        if self.side in ("auto", ""):
            return n
        wanted = {"up": Point(0, -1), "above": Point(0, -1),
                  "down": Point(0, 1), "below": Point(0, 1),
                  "left": Point(-1, 0), "right": Point(1, 0)}.get(self.side)
        if wanted is None:
            return n
        return n if n.dot(wanted) >= 0 else -n

    def path_data(self, bb: BBox = None) -> str:
        p0 = to_point(self.start_ref)
        p1 = to_point(self.end_ref)
        n = self._normal(p0, p1)
        d = self.depth
        mid = p0.lerp(p1, 0.5)
        tip = mid + n * d
        q = self.sharpness
        a1 = p0.lerp(mid, q) + n * d * 0.5
        a2 = mid.lerp(p0, 1 - q) + n * d * 0.5
        b1 = mid.lerp(p1, 1 - q) + n * d * 0.5
        b2 = p1.lerp(mid, q) + n * d * 0.5
        h0 = p0 + n * d * 0.5
        h1 = p1 + n * d * 0.5
        return (f"M{fmt(p0.x)} {fmt(p0.y)}"
                f"Q{fmt(h0.x)} {fmt(h0.y)} {fmt(a1.x)} {fmt(a1.y)}"
                f"L{fmt(a2.x)} {fmt(a2.y)}"
                f"Q{fmt(tip.x)} {fmt(tip.y)} {fmt(b1.x)} {fmt(b1.y)}"
                f"L{fmt(b2.x)} {fmt(b2.y)}"
                f"Q{fmt(h1.x)} {fmt(h1.y)} {fmt(p1.x)} {fmt(p1.y)}")

    @property
    def tip(self) -> Point:
        p0 = to_point(self.start_ref)
        p1 = to_point(self.end_ref)
        return p0.lerp(p1, 0.5) + self._normal(p0, p1) * self.depth

    def _measure(self) -> None:
        from .svgpath import path_bbox
        x0, y0, x1, y1 = path_bbox(self.path_data())
        self._x, self._y, self._w, self._h = x0, y0, x1 - x0, y1 - y0
        if self._label is not None:
            p0 = to_point(self.start_ref)
            p1 = to_point(self.end_ref)
            n = self._normal(p0, p1)
            target = self.tip + n * self.label_gap
            anchor = "center"
            if abs(n.x) > abs(n.y):
                anchor = "w" if n.x > 0 else "e"
            else:
                anchor = "n" if n.y > 0 else "s"
            self._label.at(target.x, target.y, anchor=anchor)

    @property
    def local_bbox(self) -> BBox:
        self._dirty = True
        self._ensure()
        bb = BBox(self._x, self._y, self._w or 0.0, self._h or 0.0)
        if self._label is not None:
            bb = bb.union(self._label.local_bbox)
        return bb

    @property
    def label(self) -> Text | None:
        self._ensure()
        return self._label

    def _render_content(self, ctx: RenderContext):
        attrs = paint_attrs(self, ctx)
        attrs["fill"] = "none"
        attrs.setdefault("stroke-linecap", "round")
        nodes = [Node("path", d=self.path_data(), **attrs)]
        if self._label is not None:
            self._ensure()
            n = self._label.render(ctx)
            if n is not None:
                nodes.append(n)
        return nodes


class Bracket(Brace):
    """A square bracket instead of a curly one."""

    def path_data(self, bb: BBox = None) -> str:
        p0 = to_point(self.start_ref)
        p1 = to_point(self.end_ref)
        n = self._normal(p0, p1) * self.depth
        return (f"M{fmt(p0.x)} {fmt(p0.y)}"
                f"L{fmt((p0 + n).x)} {fmt((p0 + n).y)}"
                f"L{fmt((p1 + n).x)} {fmt((p1 + n).y)}"
                f"L{fmt(p1.x)} {fmt(p1.y)}")

    @property
    def tip(self) -> Point:
        p0 = to_point(self.start_ref)
        p1 = to_point(self.end_ref)
        return p0.lerp(p1, 0.5) + self._normal(p0, p1) * self.depth


# ==========================================================================
# Legend & table
# ==========================================================================

class Legend(Group):
    """A colour/marker legend.

    >>> Legend([("train", "#4C72B0"), ("val", "#DD8452")], marker="square")
    """

    role = "group"

    def __init__(self, entries, *, marker: str = "square", swatch: float = 12.0,
                 gap: float = 7.0, row_gap: float = 6.0, cols: int = 1,
                 col_gap: float = 22.0, font_size: float = None,
                 x: float = 0.0, y: float = 0.0, **kw):
        super().__init__(**kw)
        self.rows: list = []
        items = []
        for entry in entries:
            if isinstance(entry, (tuple, list)):
                label, color = entry[0], entry[1]
                opts = entry[2] if len(entry) > 2 else {}
            else:
                label, color, opts = str(entry), "#888888", {}
            items.append((label, color, dict(opts)))

        n = len(items)
        per_col = math.ceil(n / max(1, cols))
        col_x = x
        widths = []
        for c in range(cols):
            chunk = items[c * per_col:(c + 1) * per_col]
            cy = y
            col_w = 0.0
            for label, color, opts in chunk:
                shape = opts.pop("marker", marker)
                sw = float(opts.pop("swatch", swatch))
                if shape in ("square", "rect", "box"):
                    sym = Box(None, col_x, cy, sw, sw, fill=color,
                              stroke=opts.pop("stroke", "none"), padding=0,
                              radius=opts.pop("radius", 2), add=False)
                elif shape in ("line", "dash"):
                    from .shapes import Line
                    sym = Line((col_x, cy + sw / 2), (col_x + sw * 1.4, cy + sw / 2),
                               stroke=color, stroke_width=opts.pop("lw", 2.4),
                               stroke_dash=opts.pop("dash", None), add=False)
                else:
                    sym = Marker((col_x + sw / 2, cy + sw / 2), sw, shape,
                                 fill=color, add=False)
                txt = Text(label, add=False, align="left",
                           font_size=font_size, **opts)
                txt.parent = self
                self.add(sym, txt)
                txt.at(sym.bbox.x1 + gap, sym.bbox.cy, anchor="w")
                row_h = max(sym.bbox.h, txt.bbox.h)
                col_w = max(col_w, txt.bbox.x1 - col_x)
                self.rows.append((sym, txt))
                cy += row_h + row_gap
            widths.append(col_w)
            col_x += col_w + col_gap


class Table(Group):
    """A simple table of text cells with optional header styling.

    >>> Table([["model", "acc"], ["ours", "92.1"]], header=True)
    """

    role = "group"

    def __init__(self, rows, *, header: bool = True, col_widths=None,
                 row_height: float = None, padding=(6, 10), align="left",
                 header_style=None, cell_style=None, stripe=None,
                 grid_lines: bool = True, x: float = 0.0, y: float = 0.0, **kw):
        super().__init__(**kw)
        data = [[("" if c is None else str(c)) for c in row] for row in rows]
        n_cols = max((len(r) for r in data), default=0)
        data = [r + [""] * (n_cols - len(r)) for r in data]
        pt, pr, pb, pl = _expand_spec(padding)
        aligns = align if isinstance(align, (list, tuple)) else [align] * n_cols
        aligns = list(aligns) + [aligns[-1] if aligns else "left"] * n_cols

        probes = []
        for i, row in enumerate(data):
            probe_row = []
            for j, cell in enumerate(row):
                style = header_style if (header and i == 0) else cell_style
                t = Text(cell, add=False, align=aligns[j], style=style)
                if header and i == 0 and (style is None or "font_weight" not in
                                          (style or {})):
                    t.restyle(bold=True)
                t.parent = self
                probe_row.append(t)
            probes.append(probe_row)

        if col_widths is None:
            col_widths = [max((probes[i][j].bbox.w for i in range(len(data))),
                              default=0) + pl + pr for j in range(n_cols)]
        else:
            col_widths = list(col_widths)
        rh = row_height or (max((t.bbox.h for row in probes for t in row),
                                default=14) + pt + pb)

        self.cells: list = []
        cy = y
        for i, row in enumerate(probes):
            cx = x
            row_cells = []
            for j, t in enumerate(row):
                w = col_widths[j]
                bg = None
                if header and i == 0:
                    bg = "#eef0f3"
                elif stripe and i % 2 == 0:
                    bg = stripe if isinstance(stripe, str) else "#f7f8fa"
                cell = Box(None, cx, cy, w, rh, fill=bg or "none",
                           stroke="#d7dbe0" if grid_lines else "none",
                           stroke_width=0.8, radius=0, padding=0, add=False)
                self.add(cell)
                self.add(t)
                a = aligns[j]
                if a in ("left", "start"):
                    t.at(cx + pl, cy + rh / 2, anchor="w")
                elif a in ("right", "end"):
                    t.at(cx + w - pr, cy + rh / 2, anchor="e")
                else:
                    t.at(cx + w / 2, cy + rh / 2, anchor="center")
                row_cells.append((cell, t))
                cx += w
            self.cells.append(row_cells)
            cy += rh

    def cell(self, i: int, j: int) -> Box:
        return self.cells[i][j][0]

    def cell_text(self, i: int, j: int) -> Text:
        return self.cells[i][j][1]


class Callout(Box):
    """A rounded box with a pointer tail aimed at a target point."""

    role = "box"

    def __init__(self, text=None, target=None, *, tail: float = 12.0, **kw):
        self.target_ref = target
        self.tail_w = float(tail)
        kw.setdefault("radius", 8)
        super().__init__(text, **kw)

    def shape_nodes(self, ctx: RenderContext, bb: BBox) -> list:
        nodes = super().shape_nodes(ctx, bb)
        if self.target_ref is None:
            return nodes
        tgt = to_point(self.target_ref)
        n = Point(tgt.x - bb.cx, tgt.y - bb.cy)
        if n.length == 0:
            return nodes
        base = bb.at_angle(math.degrees(math.atan2(n.y, n.x)))
        perp = Point(-n.y, n.x).normalized() * (self.tail_w / 2.0)
        attrs = paint_attrs(self, ctx, bbox=bb)
        attrs["stroke"] = "none"
        tail = Node("path", d=(f"M{fmt((base + perp).x)} {fmt((base + perp).y)}"
                               f"L{fmt(tgt.x)} {fmt(tgt.y)}"
                               f"L{fmt((base - perp).x)} {fmt((base - perp).y)}Z"),
                    **attrs)
        return list(nodes) + [tail]


class Spacer(Element):
    """An invisible element that just occupies space in a stack."""

    role = "group"

    def __init__(self, w: float = 0.0, h: float = 0.0, **kw):
        kw.setdefault("visible", False)
        super().__init__(0, 0, w, h, **kw)

    def _render_content(self, ctx: RenderContext):
        return None


def _as_grid(values, rows: int = None, cols: int = None):
    if values is None:
        return None
    seq = list(values)
    if not seq:
        return [[]]
    if isinstance(seq[0], (list, tuple)):
        return [list(r) for r in seq]
    if rows and cols:
        return [list(seq[i * cols:(i + 1) * cols]) for i in range(rows)]
    if cols:
        return [list(seq[i:i + cols]) for i in range(0, len(seq), cols)]
    if rows:
        per = math.ceil(len(seq) / rows)
        return [list(seq[i:i + per]) for i in range(0, len(seq), per)]
    return [list(seq)]


class LabelledMatrix(Component):
    """A :class:`Matrix` with its axis labels, delimiters and caption.

    The pieces of a matrix in a formula — a rotated row label, a column label,
    brackets, a caption underneath — are each trivial on their own and fiddly
    to place together. This bundles them into one movable unit.

    >>> LabelledMatrix(values, row_label="seq len", col_label="$d$",
    ...                caption="$\\Pi_{\\mathcal{NM}}$", brackets="round")

    Exposes ``.matrix``, ``.caption_text``, ``.row_text`` and ``.col_text``.
    """

    role = "group"

    def build(self, values=None, *, cell=16, row_label=None, col_label=None,
              caption=None, brackets=None, label_gap: float = 7.0,
              caption_gap: float = 9.0, bracket_gap: float = 5.0,
              label_size: float = 11.0, caption_size: float = 13.0,
              label_style=None, **matrix_kw):
        matrix = Matrix(values, cell=cell, add=False, **matrix_kw)
        self.expose("matrix", matrix)
        parts = [matrix]

        if brackets:
            parts.extend(self._delimiters(matrix, brackets, bracket_gap))
        span = BBox.union_all([p.bbox for p in parts]) or matrix.bbox

        if col_label is not None:
            top = Text(col_label, add=False, font_size=label_size,
                       style=label_style)
            top.at(span.cx, span.y0 - label_gap, anchor="s")
            self.expose("col_text", top)
            parts.append(top)
        if row_label is not None:
            side = Text(row_label, add=False, font_size=label_size,
                        style=label_style)
            side.rotate(-90)
            side.at(span.x0 - label_gap, span.cy, anchor="e")
            self.expose("row_text", side)
            parts.append(side)
        if caption is not None:
            below = Text(caption, add=False, font_size=caption_size)
            below.at(span.cx, span.y1 + caption_gap, anchor="n")
            self.expose("caption_text", below)
            parts.append(below)
        return parts

    def _delimiters(self, matrix, kind, gap: float) -> list:
        """Square or round brackets hugging the matrix."""
        box = matrix.bbox.expand(gap)
        arm = min(box.w * 0.16, 7.0)
        style = str(kind).lower()
        stroke = dict(fill="none", stroke=self.prop("color", "#16181d"),
                      stroke_width=1.2, stroke_linecap="round",
                      stroke_linejoin="round", add=False)
        if style in ("round", "paren", "()"):
            bulge = max(6.0, box.h * 0.14)
            left = (f"M{fmt(box.x0)} {fmt(box.y0)}"
                    f"Q{fmt(box.x0 - bulge)} {fmt(box.cy)} "
                    f"{fmt(box.x0)} {fmt(box.y1)}")
            right = (f"M{fmt(box.x1)} {fmt(box.y0)}"
                     f"Q{fmt(box.x1 + bulge)} {fmt(box.cy)} "
                     f"{fmt(box.x1)} {fmt(box.y1)}")
        else:
            left = (f"M{fmt(box.x0 + arm)} {fmt(box.y0)}H{fmt(box.x0)}"
                    f"V{fmt(box.y1)}H{fmt(box.x0 + arm)}")
            right = (f"M{fmt(box.x1 - arm)} {fmt(box.y0)}H{fmt(box.x1)}"
                     f"V{fmt(box.y1)}H{fmt(box.x1 - arm)}")
        from .shapes import Path
        return [Path(left, **stroke), Path(right, **stroke)]
