# Changelog

All notable changes to figkit are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and figkit uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — unreleased

First public release.

### Layout and geometry

- Elements with live anchors (`box.e` re-resolves on read, so arrows follow
  the things they connect), exact bounding boxes, and chainable relative
  placement: `at`, `right_of`, `left_of`, `above_of`, `below_of`, `inside`,
  `align_to`, `span_x`, `resize`, `rotate`, `scale_by`.
- Batch arrangement: `align`, `distribute_h/v`, `spread_h/v`, `hstack`,
  `vstack`, `grid`, `fit`, `circular`, `same_size`, `brace_around`.
- `hstack(align="baseline")` sets mixed text and matrices like an equation.
- Groups that own their children and report live bounds, with `z`-ordering.

### Text

- Text measured from real glyph advances via fontTools, with font resolution
  through registered fonts, the usual system directories and `fc-match`, and a
  fallback to the PostScript core-font metrics.
- Multi-line text, word wrapping, optical (cap-height) centring inside shapes.
- Inline `$math$` anywhere, typeset to vector outlines through matplotlib's
  mathtext, or a real `latex` + `dvisvgm` toolchain when one is installed.
- `Span` for per-word colour, weight, style, size, family, strike-through and
  underline. Decorations are drawn as geometry, so they survive rasterising
  and outlining.

### Drawing

- Shapes: `Box`, `Pill`, `Ellipse`, `Circle`, `Diamond`, `Triangle`,
  `Hexagon`, `Parallelogram`, `Chevron`, `Star`, `Cylinder`, `Note`,
  `Callout`; geometry primitives `Line`, `Polyline`, `Polygon`, `Path`,
  `Dot`, `Marker`.
- Connectors: straight, orthogonal (`elbow`), curved, arcs, explicit
  waypoints, nine arrow-head shapes, path labels, and `self_loop`.
- Composites: `Matrix`, `LabelledMatrix`, `Vector`, `ColorBar`, `Table`,
  `Legend`, `Brace`, `Bracket`, `Panel`.
- `Component` for reusable units that publish named anchors.
- `Image` embeds rasters as data URIs and inlines SVGs as vectors, rewriting
  internal ids so repeated copies never collide.

### Style

- A cascading theme: base tokens, per-role overrides, CSS-style classes and a
  colour palette, resolved kwargs → style → classes → inherited → theme →
  default.
- Seven built-in themes: default, `PAPER`, `SLIDE`, `DARK`, `BLUEPRINT`,
  `MINIMAL`, `SOFT`.
- Colour helpers: `mix`, `lighten`, `darken`, `alpha`, `saturate`,
  `contrast_color`, `colormap`, `palette`.

### Data

- `Frame` maps a data domain onto figure coordinates; `line`, `scatter`,
  `bars`, `area_fill`, `region`, `axes`, `gridlines`, log scales and
  `nice_ticks`. Every mark is an ordinary element you can anchor to.

### Checking and output

- `fig.audit()` reports overlapping elements, labels escaping their shapes,
  unreadable colour combinations, connectors crossing unrelated elements,
  degenerate geometry and content outside a pinned canvas — and is built to
  stay quiet about deliberate overlap, so a clean report means something.
- Export to SVG and HTML with no dependencies; PNG and PDF through cairosvg,
  `rsvg-convert`, `resvg`, `inkscape` or headless Chromium. Raster and PDF
  output outlines text so it cannot depend on the renderer's fonts.
- `AI_MANUAL.md`, a system-prompt-sized guide for driving figkit from an
  agent.
