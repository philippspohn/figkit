"""Colour parsing, manipulation and colormaps (no third-party deps)."""

from __future__ import annotations

import colorsys
import math
import re
from typing import Sequence

__all__ = [
    "parse_color", "to_hex", "rgba", "mix", "lighten", "darken",
    "saturate", "desaturate", "alpha", "contrast_color", "colormap",
    "PALETTES", "COLORMAPS",
]

# A small set of useful named colours (CSS names people actually reach for).
NAMED = {
    "transparent": (0, 0, 0, 0.0), "none": None,
    "black": (0, 0, 0), "white": (255, 255, 255),
    "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
    "yellow": (255, 255, 0), "orange": (255, 165, 0), "purple": (128, 0, 128),
    "gray": (128, 128, 128), "grey": (128, 128, 128),
    "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211),
    "darkgray": (169, 169, 169), "darkgrey": (169, 169, 169),
    "whitesmoke": (245, 245, 245), "gainsboro": (220, 220, 220),
    "silver": (192, 192, 192), "dimgray": (105, 105, 105),
    "navy": (0, 0, 128), "teal": (0, 128, 128), "olive": (128, 128, 0),
    "maroon": (128, 0, 0), "lime": (0, 255, 0), "aqua": (0, 255, 255),
    "cyan": (0, 255, 255), "magenta": (255, 0, 255), "fuchsia": (255, 0, 255),
    "pink": (255, 192, 203), "brown": (165, 42, 42), "gold": (255, 215, 0),
    "beige": (245, 245, 220), "ivory": (255, 255, 240), "khaki": (240, 230, 140),
    "salmon": (250, 128, 114), "coral": (255, 127, 80), "tomato": (255, 99, 71),
    "crimson": (220, 20, 60), "indigo": (75, 0, 130), "violet": (238, 130, 238),
    "steelblue": (70, 130, 180), "skyblue": (135, 206, 235),
    "lightblue": (173, 216, 230), "royalblue": (65, 105, 225),
    "cornflowerblue": (100, 149, 237), "midnightblue": (25, 25, 112),
    "seagreen": (46, 139, 87), "forestgreen": (34, 139, 34),
    "lightgreen": (144, 238, 144), "darkgreen": (0, 100, 0),
    "slategray": (112, 128, 144), "lightslategray": (119, 136, 153),
    "aliceblue": (240, 248, 255), "lavender": (230, 230, 250),
    "linen": (250, 240, 230), "snow": (255, 250, 250),
}

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3,8})$")
_FUNC_RE = re.compile(r"^(rgba?|hsla?)\(([^)]*)\)$", re.I)


def parse_color(c) -> tuple | None:
    """Parse any colour spec into ``(r, g, b, a)`` with 0-255 ints and 0-1 alpha.

    Returns ``None`` for ``"none"``/``None`` (meaning "do not paint").
    Accepts: hex (``#rgb``, ``#rgba``, ``#rrggbb``, ``#rrggbbaa``), CSS
    ``rgb()``/``rgba()``/``hsl()``/``hsla()``, named colours, ``(r, g, b)`` and
    ``(r, g, b, a)`` tuples.
    """
    if c is None:
        return None
    if isinstance(c, (tuple, list)):
        vals = list(c)
        if len(vals) == 3:
            return (_i(vals[0]), _i(vals[1]), _i(vals[2]), 1.0)
        if len(vals) == 4:
            return (_i(vals[0]), _i(vals[1]), _i(vals[2]), float(vals[3]))
        raise ValueError(f"bad colour tuple: {c!r}")
    s = str(c).strip()
    if not s:
        return None
    low = s.lower()
    if low == "none":
        return None
    if low in NAMED:
        v = NAMED[low]
        if v is None:
            return None
        return (v[0], v[1], v[2], v[3] if len(v) > 3 else 1.0)
    m = _HEX_RE.match(s)
    if m:
        h = m.group(1)
        if len(h) == 3:
            r, g, b = (int(ch * 2, 16) for ch in h)
            return (r, g, b, 1.0)
        if len(h) == 4:
            r, g, b, a = (int(ch * 2, 16) for ch in h)
            return (r, g, b, a / 255.0)
        if len(h) == 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
        if len(h) == 8:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16),
                    int(h[6:8], 16) / 255.0)
        raise ValueError(f"bad hex colour: {s!r}")
    m = _FUNC_RE.match(s)
    if m:
        kind = m.group(1).lower()
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(2)) if p.strip()]
        if kind.startswith("rgb"):
            r, g, b = (_pct(p, 255) for p in parts[:3])
            a = _alpha(parts[3]) if len(parts) > 3 else 1.0
            return (_i(r), _i(g), _i(b), a)
        hh = float(parts[0].rstrip("deg")) / 360.0
        ss = _pct(parts[1], 1.0)
        ll = _pct(parts[2], 1.0)
        a = _alpha(parts[3]) if len(parts) > 3 else 1.0
        r, g, b = colorsys.hls_to_rgb(hh % 1.0, ll, ss)
        return (_i(r * 255), _i(g * 255), _i(b * 255), a)
    raise ValueError(f"cannot parse colour {c!r}")


def _i(v) -> int:
    return max(0, min(255, int(round(float(v)))))


def _pct(tok: str, scale: float) -> float:
    tok = str(tok)
    if tok.endswith("%"):
        return float(tok[:-1]) / 100.0 * scale
    return float(tok)


def _alpha(tok: str) -> float:
    tok = str(tok)
    if tok.endswith("%"):
        return float(tok[:-1]) / 100.0
    return float(tok)


def to_hex(c, keep_alpha: bool = True) -> str:
    """Render a colour as a hex string (``#rrggbb`` or ``#rrggbbaa``)."""
    p = parse_color(c)
    if p is None:
        return "none"
    r, g, b, a = p
    if keep_alpha and a < 1.0:
        return f"#{r:02x}{g:02x}{b:02x}{_i(a * 255):02x}"
    return f"#{r:02x}{g:02x}{b:02x}"


def rgba(c, a: float) -> str:
    """Return colour ``c`` with alpha replaced by ``a``."""
    return alpha(c, a)


def alpha(c, a: float) -> str:
    """Return colour ``c`` with its alpha replaced by ``a`` (0..1)."""
    p = parse_color(c)
    if p is None:
        return "none"
    r, g, b, _ = p
    return f"rgba({r},{g},{b},{round(float(a), 4)})"


def mix(c1, c2, t: float = 0.5) -> str:
    """Linear blend: ``t=0`` gives ``c1``, ``t=1`` gives ``c2``."""
    a = parse_color(c1) or (0, 0, 0, 0.0)
    b = parse_color(c2) or (0, 0, 0, 0.0)
    t = max(0.0, min(1.0, float(t)))
    out = tuple(_i(a[i] + (b[i] - a[i]) * t) for i in range(3))
    aa = a[3] + (b[3] - a[3]) * t
    return to_hex((out[0], out[1], out[2], aa))


def lighten(c, amount: float = 0.2) -> str:
    """Move a colour toward white (``amount`` in 0..1)."""
    return mix(c, "#ffffff", amount)


def darken(c, amount: float = 0.2) -> str:
    """Move a colour toward black (``amount`` in 0..1)."""
    return mix(c, "#000000", amount)


def _hls(c):
    p = parse_color(c) or (0, 0, 0, 1.0)
    h, l, s = colorsys.rgb_to_hls(p[0] / 255, p[1] / 255, p[2] / 255)
    return h, l, s, p[3]


def saturate(c, amount: float = 0.2) -> str:
    """Increase saturation by ``amount`` (0..1); negative desaturates."""
    h, l, s, a = _hls(c)
    r, g, b = colorsys.hls_to_rgb(h, l, max(0.0, min(1.0, s + amount)))
    return to_hex((r * 255, g * 255, b * 255, a))


def desaturate(c, amount: float = 0.2) -> str:
    """Wash a colour out toward grey by ``amount`` (0..1)."""
    return saturate(c, -amount)


def luminance(c) -> float:
    """Relative luminance per WCAG."""
    p = parse_color(c)
    if p is None:
        return 1.0

    def ch(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(p[0]) + 0.7152 * ch(p[1]) + 0.0722 * ch(p[2])


def contrast_color(bg, dark="#111111", light="#ffffff") -> str:
    """Pick whichever of ``dark``/``light`` reads better on ``bg``."""
    return dark if luminance(bg) > 0.45 else light


# --------------------------------------------------------------------------
# Palettes
# --------------------------------------------------------------------------

PALETTES = {
    # Muted, print-friendly default: works well for ML paper figures.
    "figkit": ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
               "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD"],
    "tab10": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
              "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"],
    "pastel": ["#a1c9f4", "#ffb482", "#8de5a1", "#ff9f9b", "#d0bbff",
               "#debb9b", "#fab0e4", "#cfcfcf", "#fffea3", "#b9f2f0"],
    "bold": ["#7F3C8D", "#11A579", "#3969AC", "#F2B701", "#E73F74",
             "#80BA5A", "#E68310", "#008695", "#CF1C90", "#f97b72"],
    "grays": ["#111111", "#444444", "#777777", "#999999", "#bbbbbb", "#dddddd"],
}

# Compact colormap definitions: anchor stops that get interpolated.
COLORMAPS = {
    "viridis": ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"],
    "plasma": ["#0d0887", "#6a00a8", "#b12a90", "#e16462", "#fca636", "#f0f921"],
    "magma": ["#000004", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"],
    "inferno": ["#000004", "#420a68", "#932667", "#dd513a", "#fca50a", "#fcffa4"],
    "cividis": ["#00224e", "#123570", "#3b496c", "#575d6d", "#707173", "#8a8678",
                "#a59c74", "#c3b369", "#e1cc55", "#fee838"],
    "gray": ["#000000", "#ffffff"],
    "grey": ["#000000", "#ffffff"],
    "grays": ["#ffffff", "#111111"],
    "greys": ["#ffffff", "#111111"],
    "blues": ["#f7fbff", "#deebf7", "#c6dbef", "#9ecae1", "#6baed6",
              "#4292c6", "#2171b5", "#08519c", "#08306b"],
    "reds": ["#fff5f0", "#fee0d2", "#fcbba1", "#fc9272", "#fb6a4a",
             "#ef3b2c", "#cb181d", "#a50f15", "#67000d"],
    "greens": ["#f7fcf5", "#e5f5e0", "#c7e9c0", "#a1d99b", "#74c476",
               "#41ab5d", "#238b45", "#006d2c", "#00441b"],
    "oranges": ["#fff5eb", "#fee6ce", "#fdd0a2", "#fdae6b", "#fd8d3c",
                "#f16913", "#d94801", "#a63603", "#7f2704"],
    "purples": ["#fcfbfd", "#efedf5", "#dadaeb", "#bcbddc", "#9e9ac8",
                "#807dba", "#6a51a3", "#54278f", "#3f007d"],
    # Diverging
    "coolwarm": ["#3b4cc0", "#7b9ff9", "#c0d4f5", "#f2cbb7", "#ee8468", "#b40426"],
    "rdbu": ["#67001f", "#d6604d", "#f7f7f7", "#4393c3", "#053061"],
    "bwr": ["#0000ff", "#ffffff", "#ff0000"],
    "spectral": ["#9e0142", "#f46d43", "#fee08b", "#e6f598", "#66c2a5", "#5e4fa2"],
}


def colormap(name_or_stops, t: float) -> str:
    """Sample a colormap at ``t`` in ``[0, 1]``.

    ``name_or_stops`` is a colormap name (see :data:`COLORMAPS`), a list of
    colour stops, or a callable ``t -> colour``.
    """
    if callable(name_or_stops):
        return name_or_stops(t)
    if isinstance(name_or_stops, str):
        key = name_or_stops.lower()
        rev = key.endswith("_r")
        if rev:
            key = key[:-2]
        stops = COLORMAPS.get(key)
        if stops is None:
            raise KeyError(f"unknown colormap {name_or_stops!r}; "
                           f"available: {sorted(COLORMAPS)}")
        if rev:
            stops = list(reversed(stops))
    else:
        stops = list(name_or_stops)
    if not stops:
        return "#000000"
    if len(stops) == 1:
        return to_hex(stops[0])
    t = 0.0 if t is None or math.isnan(t) else max(0.0, min(1.0, float(t)))
    pos = t * (len(stops) - 1)
    i = min(int(pos), len(stops) - 2)
    return mix(stops[i], stops[i + 1], pos - i)


def palette(name="figkit", n: int = None) -> list:
    """Return a categorical palette, cycled/truncated to ``n`` entries."""
    cols = PALETTES.get(name) if isinstance(name, str) else list(name)
    if cols is None:
        raise KeyError(f"unknown palette {name!r}; available: {sorted(PALETTES)}")
    if n is None:
        return list(cols)
    return [cols[i % len(cols)] for i in range(n)]


def normalize(values: Sequence, vmin=None, vmax=None) -> list:
    """Scale values into ``[0, 1]`` (used for heatmaps / colour coding)."""
    vals = [float(v) for v in values]
    if not vals:
        return []
    lo = min(vals) if vmin is None else float(vmin)
    hi = max(vals) if vmax is None else float(vmax)
    if hi == lo:
        return [0.5] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]
