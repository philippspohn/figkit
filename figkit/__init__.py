"""figkit — design figures with Python code, export to SVG/PNG/PDF/HTML.

Quick start::

    from figkit import *

    with Figure(pad=24) as fig:
        a = Box("Encoder", style="block", w=120)
        b = Box("Decoder", style="blue").right_of(a, gap=60)
        arrow(a.e, b.w, label="z")
    fig.save("figure.svg")

Everything is explicit: you place things, figkit measures them accurately
(real font metrics), and anchors stay live so arrows follow their boxes.
"""

from __future__ import annotations

__version__ = "0.1.0"

# -- geometry ---------------------------------------------------------------
from .geom import Affine, BBox, Point, to_point

# -- colour -----------------------------------------------------------------
from .colors import (COLORMAPS, PALETTES, alpha, colormap, contrast_color,
                     darken, desaturate, lighten, luminance, mix, normalize,
                     palette, parse_color, rgba, saturate, to_hex)

# -- style ------------------------------------------------------------------
from .style import DEFAULT_THEME, MONO, SANS, SERIF, Style, Theme, use_theme
from .themes import (BLUEPRINT, DARK, MINIMAL, PAPER, SLIDE, SOFT, THEMES,
                     get_theme)

# -- core -------------------------------------------------------------------
from .core import Anchor, Element, Group

# -- content ----------------------------------------------------------------
from .text import Label, Text, layout_text, measure_block
from .shapes import (Box, Chevron, Circle, Cylinder, Diamond, Dot, Ellipse,
                     Hexagon, Line, Marker, Parallelogram, Path, Pill, Polygon,
                     Polyline, Rect, Shape, Stadium, Star, Triangle, Note)
from .image import Image
from .components import (Bracket, Brace, Callout, ColorBar, Heatmap, Legend,
                         Matrix, Panel, Spacer, Table, Vector)

# -- connectors -------------------------------------------------------------
from .connectors import (Connector, arrow, connect, curve, double_arrow, elbow,
                         line)

# -- layout -----------------------------------------------------------------
from .layout import (align, align_h, align_v, between, bbox_of, center_on,
                     circular, distribute_h, distribute_v, fit, frame_around,
                     grid, group, hstack, midpoint, same_height, same_size,
                     same_width, shift, spread_h, spread_v, vstack)

# -- data / plots -----------------------------------------------------------
from .frame import Frame, nice_ticks

# -- fonts & math -----------------------------------------------------------
from .fonts import get_font, measure_text, register_font, text_extents
from .mathtext import (latex_available, math_available, render_math,
                       set_latex_preamble, set_math_fontset)

# -- output -----------------------------------------------------------------
from .figure import Figure
from .export import ExportError, available_backends, save_figure

__all__ = [
    "__version__",
    # geometry
    "Point", "BBox", "Affine", "to_point",
    # colour
    "parse_color", "to_hex", "rgba", "alpha", "mix", "lighten", "darken",
    "saturate", "desaturate", "luminance", "contrast_color", "colormap",
    "palette", "normalize", "PALETTES", "COLORMAPS",
    # style / theme
    "Style", "Theme", "use_theme", "DEFAULT_THEME", "SANS", "SERIF", "MONO",
    "PAPER", "SLIDE", "DARK", "BLUEPRINT", "MINIMAL", "SOFT", "THEMES",
    "get_theme",
    # core
    "Element", "Group", "Anchor",
    # content
    "Text", "Label", "layout_text", "measure_block",
    "Shape", "Box", "Rect", "Pill", "Stadium", "Ellipse", "Circle", "Diamond",
    "Triangle", "Hexagon", "Parallelogram", "Chevron", "Star", "Cylinder",
    "Note", "Path", "Polygon", "Polyline", "Line", "Dot", "Marker",
    "Image", "Matrix", "Vector", "Heatmap", "ColorBar", "Panel", "Brace",
    "Bracket", "Legend", "Table", "Callout", "Spacer",
    # connectors
    "Connector", "arrow", "line", "elbow", "curve", "connect", "double_arrow",
    # layout
    "align", "align_h", "align_v", "distribute_h", "distribute_v", "spread_h",
    "spread_v", "hstack", "vstack", "grid", "fit", "frame_around", "between",
    "midpoint", "center_on", "group", "bbox_of", "circular", "same_width",
    "same_height", "same_size", "shift",
    # data
    "Frame", "nice_ticks",
    # fonts / math
    "get_font", "measure_text", "text_extents", "register_font",
    "render_math", "math_available", "latex_available", "set_math_fontset",
    "set_latex_preamble",
    # output
    "Figure", "save_figure", "available_backends", "ExportError",
]
