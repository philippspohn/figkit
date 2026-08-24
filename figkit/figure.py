"""The :class:`Figure` root: collects elements, sizes the canvas, exports."""

from __future__ import annotations

import base64
import os
import warnings

from .core import Group, pop_container, push_container
from .geom import Affine, BBox, _expand_spec, to_point
from .style import DEFAULT_THEME, Theme, use_theme
from .svgdoc import Node, RenderContext

__all__ = ["Figure"]

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


class Figure(Group):
    """The drawing surface.

    Use it as a context manager and every element you create is added
    automatically::

        with Figure(theme=my_theme, pad=24) as fig:
            a = Box("input")
            b = Box("model").right_of(a, gap=40)
            arrow(a.e, b.w)
        fig.save("figure.svg")

    By default the canvas is sized to fit its contents plus ``pad``.  Pass
    ``w``/``h`` to pin it instead.
    """

    role = "figure"

    def __init__(self, w: float = None, h: float = None, *, pad=24,
                 background=None, theme: Theme = None, style=None,
                 title: str = None, description: str = None,
                 viewbox: BBox = None, origin=None, scale: float = 1.0,
                 **props):
        self._fixed_w = w
        self._fixed_h = h
        self.pad = _expand_spec(pad)
        self.background = background
        self.title = title
        self.description = description
        self._viewbox = viewbox
        self._origin = origin
        self.scale = float(scale)
        self._theme_token = None
        self._container_token = None
        super().__init__(style=style, theme=theme or DEFAULT_THEME, add=False,
                         **props)
        self.parent = None

    # -- context manager -------------------------------------------------
    def __enter__(self) -> "Figure":
        self._container_token = push_container(self)
        self._theme_token = use_theme(self._theme or DEFAULT_THEME)
        self._theme_token.__enter__()
        return self

    def __exit__(self, *exc):
        if self._theme_token is not None:
            self._theme_token.__exit__(*exc)
            self._theme_token = None
        pop_container(self._container_token)
        self._container_token = None
        return False

    def child_matrix(self) -> Affine:
        return Affine.IDENTITY

    def parent_matrix(self) -> Affine:
        return Affine.IDENTITY

    # -- canvas geometry -------------------------------------------------
    def content_bbox(self) -> BBox:
        boxes = [c.ink_bbox for c in self._children if c.visible]
        bb = BBox.union_all(boxes)
        return bb if bb is not None else BBox(0, 0, 0, 0)

    @property
    def fixed_size(self) -> bool:
        """True when both dimensions were pinned, i.e. this is a canvas."""
        return self._fixed_w is not None and self._fixed_h is not None

    def viewbox(self) -> BBox:
        """The rectangle of world space that ends up in the output.

        Auto-sized figures wrap their content plus ``pad``. Giving both ``w``
        and ``h`` makes the figure a fixed canvas, whose origin is ``(0, 0)``
        so that coordinates mean what they say — pass ``origin=`` to move it,
        or ``origin="content"`` for the auto-sized behaviour.
        """
        if self._viewbox is not None:
            return self._viewbox
        content = self.content_bbox()
        top, right, bottom, left = self.pad
        bb = content.expand(0, top=top, right=right, bottom=bottom, left=left)
        if self._fixed_w is not None:
            bb = BBox(bb.x, bb.y, float(self._fixed_w), bb.h)
        if self._fixed_h is not None:
            bb = BBox(bb.x, bb.y, bb.w, float(self._fixed_h))
        anchor = self._origin
        if anchor is None and self.fixed_size:
            anchor = (0.0, 0.0)      # a pinned canvas starts at the origin
        if anchor is not None and anchor != "content":
            p = to_point(anchor)
            bb = BBox(p.x, p.y, bb.w, bb.h)
        if bb.w <= 0:
            bb = BBox(bb.x, bb.y, 1.0, bb.h)
        if bb.h <= 0:
            bb = BBox(bb.x, bb.y, bb.w, 1.0)
        return bb

    @property
    def size(self):
        vb = self.viewbox()
        from .geom import Point
        return Point(vb.w * self.scale, vb.h * self.scale)

    def set_viewbox(self, x, y=None, w=None, h=None) -> "Figure":
        """Pin the visible rectangle explicitly."""
        self._viewbox = x if isinstance(x, BBox) else BBox(x, y, w, h)
        return self

    def fit_contents(self, pad=None) -> "Figure":
        """Drop any pinned viewbox or fixed size and go back to auto-sizing."""
        self._viewbox = None
        self._fixed_w = self._fixed_h = None
        self._origin = None
        if pad is not None:
            self.pad = _expand_spec(pad)
        return self

    # -- rendering -------------------------------------------------------
    def render_context(self, **opts) -> RenderContext:
        return RenderContext(theme=self._theme or DEFAULT_THEME, **opts)

    def to_svg(self, *, pretty: bool = True, text_as_paths: bool = False,
               embed_fonts: bool = False, standalone: bool = True,
               scale: float = None, width: float = None,
               height: float = None) -> str:
        """Render to an SVG document string."""
        ctx = self.render_context(text_as_paths=text_as_paths,
                                  embed_fonts=embed_fonts, pretty=pretty)
        vb = self.viewbox()
        body_nodes = []
        kids = sorted([c for c in self._children if c.visible],
                      key=lambda c: (getattr(c, "z", 0) or 0))
        for child in kids:
            node = child.render(ctx)
            if node is not None:
                body_nodes.append(node)

        sc = self.scale if scale is None else float(scale)
        out_w = width if width is not None else vb.w * sc
        out_h = height if height is not None else vb.h * sc

        svg = Node("svg", xmlns=SVG_NS, xmlns__xlink=XLINK_NS,
                   width=_len(out_w), height=_len(out_h),
                   viewBox=f"{_n(vb.x)} {_n(vb.y)} {_n(vb.w)} {_n(vb.h)}")
        if self.title:
            svg.add(Node("title", text=self.title))
        if self.description:
            svg.add(Node("desc", text=self.description))

        if embed_fonts:
            css = _font_face_css(ctx)
            if css:
                svg.add(Node("style", raw=css, type="text/css"))
        if ctx.defs:
            defs = Node("defs")
            defs.add(*ctx.defs)
            svg.add(defs)
        bg = self.background if self.background is not None else \
            self.prop("background", None)
        if bg and str(bg).lower() != "none":
            svg.add(Node("rect", x=vb.x, y=vb.y, width=vb.w, height=vb.h,
                         fill=bg))
        svg.add(*body_nodes)

        for message in ctx.warnings:
            warnings.warn(f"figkit: {message}", stacklevel=2)
        head = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' \
            if standalone else ""
        return head + svg.render(0, pretty)

    def _repr_svg_(self) -> str:
        """Rich display in Jupyter."""
        return self.to_svg(standalone=False)

    def to_html(self, *, title: str = None, embed: bool = True,
                background: str = "#ffffff", **svg_kw) -> str:
        """A standalone HTML page wrapping the SVG.

        ``embed=True`` leaves the SVG inline and styleable. ``embed=False``
        isolates it in an ``<img>`` data URI.
        """
        svg = self.to_svg(standalone=False, **svg_kw)
        heading = title or self.title or "figure"
        if embed:
            body = svg
        else:
            payload = base64.b64encode(svg.encode("utf-8")).decode("ascii")
            body = (f'<img alt="{_esc(heading)}" '
                    f'src="data:image/svg+xml;base64,{payload}">')
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(heading)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: {background}; padding: 24px; box-sizing: border-box;
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
  .figkit-wrap {{ max-width: 100%; }}
  .figkit-wrap svg, .figkit-wrap img {{ max-width: 100%; height: auto; display: block; }}
</style>
</head>
<body>
<div class="figkit-wrap">
{body}
</div>
</body>
</html>
"""

    # -- saving ----------------------------------------------------------
    def save(self, path, *, scale: float = None, dpi: float = None,
             format: str = None, **kw) -> str:
        """Write the figure to ``.svg``, ``.png``, ``.pdf`` or ``.html``.

        >>> fig.save("out.svg")
        >>> fig.save("out.png", scale=2)      # 2x pixel density
        >>> fig.save("out.pdf")
        """
        from .export import save_figure
        return save_figure(self, path, scale=scale, dpi=dpi, format=format, **kw)

    def to_png(self, path=None, *, scale: float = 2.0, **kw):
        from .export import to_png
        return to_png(self, path, scale=scale, **kw)

    def to_pdf(self, path=None, **kw):
        from .export import to_pdf
        return to_pdf(self, path, **kw)

    def audit(self, **options):
        """Check the figure for the mistakes you would otherwise spot by eye.

        Returns a :class:`~figkit.audit.Report` that is falsy when nothing
        looks wrong, so ``print(fig.audit())`` is usually all you need::

            with Figure() as fig:
                ...
            print(fig.audit())

        See :func:`figkit.audit.audit` for the individual checks and how to
        switch them off.
        """
        from .audit import audit as run_audit
        return run_audit(self, **options)

    def show(self, path=None) -> str:
        """Write an HTML preview and return its path (handy while iterating)."""
        path = path or "figure.html"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_html())
        return os.path.abspath(path)

    def __repr__(self) -> str:
        vb = self.viewbox()
        return (f"<Figure {len(self._children)} elements "
                f"{vb.w:.4g}x{vb.h:.4g}>")


def _n(v: float) -> str:
    from .svgpath import fmt
    return fmt(v)


def _len(v: float) -> str:
    from .svgpath import fmt
    return fmt(v)


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _font_face_css(ctx: RenderContext) -> str:
    """Base64 ``@font-face`` rules for every font actually used."""
    import base64

    from .fonts import get_font

    rules = []
    seen = set()
    for family, weight, style in sorted(ctx.fonts_used, key=lambda t: str(t)):
        font = get_font(family, weight, style)
        if not font.available or font.path in seen:
            continue
        data = font.font_data()
        if not data or len(data) > 6_000_000:
            continue
        seen.add(font.path)
        ext = os.path.splitext(font.path)[1].lower()
        fmt_name = {".otf": "opentype", ".ttf": "truetype",
                    ".woff": "woff", ".woff2": "woff2"}.get(ext, "truetype")
        b64 = base64.b64encode(data).decode("ascii")
        primary = str(family).split(",")[0].strip().strip("'\"")
        rules.append(
            f"@font-face{{font-family:'{primary}';"
            f"font-weight:{font.weight};font-style:{font.style};"
            f"src:url(data:font/{fmt_name};base64,{b64}) format('{fmt_name}');}}")
    return "\n".join(rules)
