"""Turning resolved style properties into SVG paint attributes."""

from __future__ import annotations

from .colors import parse_color, to_hex
from .style import normalize_dash
from .svgdoc import Node, RenderContext

__all__ = ["paint_attrs", "shadow_filter", "gradient_paint"]


def gradient_paint(spec, ctx: RenderContext, bbox=None) -> str:
    """Register a gradient definition and return a ``url(#id)`` reference.

    ``spec`` is a dict like ``{"type": "linear", "stops": ["#fff", "#000"],
    "angle": 90}`` or ``{"type": "radial", "stops": [(0, "#fff"), (1, "#000")]}``.
    """
    kind = str(spec.get("type", "linear")).lower()
    stops = spec.get("stops") or ["#ffffff", "#000000"]
    norm = []
    for i, st in enumerate(stops):
        if isinstance(st, (tuple, list)) and len(st) >= 2:
            offset, color = float(st[0]), st[1]
            opacity = st[2] if len(st) > 2 else None
        else:
            offset = i / max(1, len(stops) - 1)
            color, opacity = st, None
        norm.append((offset, color, opacity))

    if kind.startswith("rad"):
        node = Node("radialGradient",
                    cx=spec.get("cx", 0.5), cy=spec.get("cy", 0.5),
                    r=spec.get("r", 0.5))
    else:
        import math
        angle = float(spec.get("angle", 0.0))
        a = math.radians(angle)
        dx, dy = math.cos(a) / 2.0, math.sin(a) / 2.0
        node = Node("linearGradient",
                    x1=0.5 - dx, y1=0.5 - dy, x2=0.5 + dx, y2=0.5 + dy)
    for offset, color, opacity in norm:
        node.add(Node("stop", offset=round(offset, 4), stop_color=to_hex(color),
                      stop_opacity=opacity))
    return f"url(#{ctx.add_def(node)})"


def shadow_filter(spec, ctx: RenderContext) -> str:
    """Register a drop-shadow filter and return a ``url(#id)`` reference."""
    if spec is True:
        spec = {}
    if not isinstance(spec, dict):
        spec = {}
    dx = spec.get("dx", 0)
    dy = spec.get("dy", 2)
    blur = spec.get("blur", 4)
    color = to_hex(spec.get("color", "#000000"), keep_alpha=False)
    opacity = spec.get("opacity", 0.18)
    node = Node("filter", x="-40%", y="-40%", width="180%", height="180%",
                color_interpolation_filters="sRGB")
    node.add(Node("feDropShadow", dx=dx, dy=dy, stdDeviation=blur,
                  flood_color=color, flood_opacity=opacity))
    key = f"shadow:{dx}:{dy}:{blur}:{color}:{opacity}"
    return f"url(#{ctx.add_def(node, key)})"


def _color(value, ctx: RenderContext, bbox=None):
    """Resolve a paint value to ``(paint, opacity_or_None)``."""
    if value is None:
        return None, None
    if isinstance(value, dict):
        return gradient_paint(value, ctx, bbox), None
    if isinstance(value, (tuple, list)):
        value = to_hex(value)
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("url(") or s.startswith("var(") or s.lower() == "none":
            return s, None
        # Split any alpha out into a separate attribute: 8-digit hex and
        # rgba()/hsla() are not universally supported by SVG rasterisers.
        try:
            parsed = parse_color(s)
        except ValueError:
            return s, None
        if parsed is None:
            return "none", None
        r, g, b, a = parsed
        if a < 1.0:
            return f"#{r:02x}{g:02x}{b:02x}", round(a, 4)
        if len(s) > 7 or not s.startswith("#"):
            return f"#{r:02x}{g:02x}{b:02x}", None
        return s, None
    return value, None


def paint_attrs(el, ctx: RenderContext, *, fill: bool = True,
                stroke: bool = True, bbox=None) -> dict:
    """Resolve fill/stroke/dash/etc. for an element into SVG attributes."""
    attrs: dict = {}
    if fill:
        f, f_alpha = _color(el.prop("fill", None), ctx, bbox)
        attrs["fill"] = "none" if f is None else f
        fo = el.prop("fill_opacity", None)
        fo = f_alpha if fo is None else (
            float(fo) * f_alpha if f_alpha is not None else float(fo))
        if fo is not None:
            attrs["fill-opacity"] = round(float(fo), 4)
    if stroke:
        s, s_alpha = _color(el.prop("stroke", None), ctx, bbox)
        sw = el.prop("stroke_width", None)
        if s in (None, "none") or not sw:
            attrs["stroke"] = "none"
        else:
            attrs["stroke"] = s
            attrs["stroke-width"] = sw
            if s_alpha is not None:
                attrs["stroke-opacity"] = s_alpha
            dash = normalize_dash(el.prop("stroke_dash", None))
            if dash:
                attrs["stroke-dasharray"] = dash
                off = el.prop("stroke_dashoffset", None)
                if off:
                    attrs["stroke-dashoffset"] = off
            cap = el.prop("stroke_linecap", None)
            if cap and cap != "butt":
                attrs["stroke-linecap"] = cap
            join = el.prop("stroke_linejoin", None)
            if join and join != "miter":
                attrs["stroke-linejoin"] = join
            so = el.prop("stroke_opacity", None)
            if so is not None:
                attrs["stroke-opacity"] = (round(float(so) * s_alpha, 4)
                                           if s_alpha is not None else so)
    shadow = el.prop("shadow", None)
    if shadow:
        attrs["filter"] = shadow_filter(shadow, ctx)
    return attrs
