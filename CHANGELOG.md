# Changelog

All notable changes to figkit are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and figkit uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-08-24

### Changed

- **A style property figkit does not read now raises `UnknownProperty`**
  instead of being stored and ignored. `Text("hi", sizee=8)` used to render at
  the theme default with no complaint; it now fails with a suggestion. This is
  a breaking change for code passing properties that never did anything.
  Components with properties of their own declare them with
  `register_props(...)`, and `PROPS` is the full list.
- **`rotate=` on `Text` turns the block about `(x, y)`**, not about its own
  centre. Pivoting on the centre displaced the text by half its own length, so
  where a rotated label landed depended on how many characters it had — a
  50pt label drifted 25pt. `rotate_about=` takes an explicit pivot, and
  `el.rotate(deg)` after construction is unchanged.
- Arrow heads shrink to fit connectors too short to hold them. A head larger
  than the connector used to consume the whole shaft and overshoot its start,
  drawing a stray triangle with no line.
- String options such as connector routes, marker shapes, grid order/alignment,
  vector orientation, frame scales/sides and image fit now reject invalid
  values with a suggestion instead of silently choosing another rendering.
- Raster export now rejects `.jpg`, `.jpeg` and `.webp`; these extensions were
  accepted even though the bytes written were always PNG.

### Added

- `size=` is an alias for `font_size=`, matching `measure_text(..., size=)`.
  Measuring at one size and rendering at another was silent before.
- `fill=` set directly on a `Text` means its colour. Text has no fill of its
  own, so the property was being dropped.
- A warning when the font has no glyph for a character: it renders as an empty
  box and its measured width is `.notdef`'s, not the character's, so layout
  computed from it is wrong. Names the codepoint, warns once per font and
  character.
- `Dot` accepts `Dot(x, y, r=...)` as well as `Dot(center, r)`, matching
  `Circle` and every other element's `x, y` front door.
- `word_spacing=` participates in both measurement and SVG/path rendering, and
  `text_transform=` supports `none`, `uppercase`, `lowercase` and `capitalize`.
  The advertised but unimplemented `font_variant` property is now rejected
  instead of being accepted as a silent no-op.
- `rotate=` and `rotate_about=` are common element constructor options, as the
  manual already claimed, rather than Text-only constructor options. The
  rotation is applied on first measurement rather than in `Element.__init__`,
  because a subclass has not sized itself yet at that point: pivoting there
  used the placeholder box, so a label-sized element landed somewhere that
  depended on how long its text was.
- `Figure.to_html(embed=False)` isolates the SVG in an image data URI;
  `embed=True` keeps the SVG inline and styleable.

### Documentation

- The manual led with "nothing is auto-laid-out", which read as an instruction
  to place everything by hand. It now points at `hstack`/`vstack`/`grid`/`fit`
  and the existing `Matrix`, `Table`, `Brace` and `Legend` components first.
- Every style property and its aliases are tabulated, so valid names no longer
  have to be discovered by reading theme reprs.
- Gotchas for the rotation pivot, missing glyphs, small-`Box` corner radius,
  short-connector heads, and the macOS `DYLD_FALLBACK_LIBRARY_PATH` fix for
  cairosvg.

### Fixed

- `figkit.__version__` reported `0.1.0` from the 0.1.1 release. The number
  lived in both `pyproject.toml` and `figkit/__init__.py`, and a release only
  bumped the first. `pyproject.toml` now reads the version from the package,
  so there is one number to change and it cannot drift again.
- macOS `.ttc`/`.otc` system fonts failed to load because the collection
  loader received a TTFont-only argument. Collections now select the closest
  family/weight/style face, restoring accurate metrics and text outlines.
- `hstack(..., at=...)` and `vstack(..., at=...)` now place the north-west
  corner of the completed result at `at`, including an optional panel.
- `max_w=` now constrains and reflows a shape's label, including long tokens,
  instead of shrinking only the container and leaving its text outside.
- `self_loop()` keeps live anchors for its feet and apex, so it follows an
  element after movement or resizing.
- `Frame(clip_data=True)` clips only data marks; axes, ticks and titles remain
  visible outside the plot area.
- `Matrix.highlight()` keeps the highlighted cell's value label in front.
- Contrast audit uses the same resolved text colour as rendering, including
  `Text(fill=...)` and per-Span colours.
- `ColorBar` segments stay within the declared strip bounds.
- Dict-valued theme fills such as gradients are no longer mistaken for roles.
- Math glyph left overhang is included in measurement and normalized in the
  generated path.
- Rich `Text` content has a safe repr, and outlined missing glyphs now draw the
  `.notdef` box described by their warning instead of leaving a blank gap.

## [0.1.1] — 2026-08-21

### Connectors

- `start_handle=` and `end_handle=` place either end's Bezier handle — the
  "whisker" a vector editor lets you drag. The direction is the asymptote the
  curve leaves along, the length is how long it clings to it, given as a
  fraction of the endpoint separation so the shape survives the layout
  moving. Takes a bare fraction, a tuple, or a `Handle` (which also offers
  `px=` for an absolute reach). An end given a handle ignores `bend`/`bow`.
- Handles also give curves between bare points a direction to leave in, which
  previously only anchors could supply.
- `tension=` (default 0.5) loosens the spline threaded through `waypoints=`.

### Fixed

- A curve with waypoints threw its endpoint normals away, so `curve(a.e, b.w,
  waypoints=[p])` left the box diagonally instead of along the face it was
  attached to. The outer tangents are now pinned to the attachment normals.

## [0.1.0] — 2026-08-21

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
