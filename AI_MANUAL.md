# figkit — agent manual

figkit builds **publication-quality figures from Python code** and exports them
to SVG / PNG / PDF / HTML. It targets the diagrams in ML papers and research
blog posts: pipelines, boxes-and-arrows, annotated matrices, LaTeX labels,
data-driven graphics.

Use it when the user wants a *diagram, figure, schematic or pipeline drawing*
that should be reproducible and editable as code. It is not a plotting library
(though it can draw plots) and not a general canvas API.

```python
from figkit import *

with Figure(pad=24) as fig:                     # auto-collects everything below
    a = Box("Encoder", style="block", w=120)
    b = Box("Decoder", style="blue").right_of(a, gap=60)
    arrow(a.e, b.w, label="$z$")

print(fig.audit())                              # ← check before you export
fig.save("figure.svg")
fig.save("figure.png", scale=2)                 # 2x pixel density
```

**Always run `fig.audit()` before you finish.** It catches, without rendering
anything, the mistakes you would otherwise only see by looking at the picture:
overlapping elements, labels sticking out of their boxes, unreadable colour
combinations, arrows through boxes they do not connect. It prints one line per
problem with coordinates, and `no issues` when the figure is clean.

---

## 1. Mental model — read this before writing code

* **Units are px. `y` grows downward** (SVG convention): `n` is the top edge,
  `s` the bottom.
* **Nothing is auto-laid-out.** You place things; figkit measures them
  accurately (real font metrics from the font file) so relative placement is
  exact.
* **Anchors are live references.** `box.e` is not a coordinate — it resolves
  when read. Move the box afterwards and every arrow pointing at it follows.
* **Every placement call returns `self`**, so it chains:
  `Box("x").right_of(a, gap=20).align_to(b, "top")`.
* **Sizes are intrinsic unless you pin them.** `Box("hello")` sizes to its
  text plus padding; `Box("hello", w=200)` pins the width and wraps the text.
* **Paint order = child order** (later draws on top). `z=` sorts within a
  parent; `to_front()` / `to_back()` reorder.
* **A figure auto-sizes to its contents.** Giving both `w` and `h` makes it a
  fixed canvas whose origin is `(0, 0)`, so coordinates mean what they say;
  pass `origin=` to move it or `origin="content"` for the auto-sized rule.
* **Create the `Figure` first**, then the elements. Elements resolve their
  theme through their parent, so `with Figure(theme=T) as fig:` makes `T`
  apply to everything created inside. (The ambient figure and theme live in
  `contextvars`, so concurrent threads/tasks don't interfere.)

---

## 2. Cheat sheet

| Need | Call |
|---|---|
| canvas | `Figure(w=None, h=None, pad=24, background=None, theme=None)` |
| fixed canvas | `Figure(764, 620, pad=0)` — origin is `(0, 0)` |
| box with text | `Box("label", w=..., h=..., style="blue")` |
| plain text | `Text("hi", bold=True, font_size=16, align="left")` |
| styled spans | `Text(["ok ", Span("bad", color="@bad", strike=True)])` |
| math | put `$...$` anywhere in a string: `Box("$F_{\mathcal{M}}$")` |
| absolute place | `el.at(x, y, anchor="nw")`, `el.center_at(x, y)` |
| relative place | `el.right_of(other, gap=24, align="top", dx=0, dy=0)` |
| put inside | `el.inside(other, anchor="se", pad=8)` |
| anchor | `el.n .s .e .w .ne .nw .se .sw .center`, `el.at_angle(30)`, `el.uv(u, v)` |
| anchor on an arrow | `c.mid`, `c.anchor_at(0.25)` — live, follows the arrow |
| offset anchor | `el.e + (6, 0)` |
| arrow | `arrow(a.e, b.w, label="x")` |
| orthogonal | `elbow(a.e, b.w, stub=14, corner=6)` |
| curved | `curve(a.s, b.s, bend=0.4)` |
| shaped curve | `curve(a.e, b.w, start_handle=0.6, end_handle=(0.2, -30))` |
| align a group | `align([a, b, c], "top")` |
| even spacing | `distribute_h(items, gap=20)` / `spread_h(items, x0, x1)` |
| row / column | `hstack(items, gap=16, align="center")` / `vstack(...)` |
| formula row | `hstack([lhs, matrix, rhs], gap=8, align="baseline")` |
| grid | `grid(items, cols=3, gap=(20, 14))` |
| container box | `fit(a, b, pad=20, label="stage 1", dash=True)` |
| self-loop | `self_loop(state, side="top", label="retry")` |
| brace over a set | `brace_around([a, b, c], side="top", label="stage")` |
| midpoint | `between(a, b)` |
| bounds only | `bbox_of([a, b, c])` |
| data space | `fr = Frame(w=400, h=220, xlim=(0,10), ylim=(0,1))`; `fr.pt(x, y)` |
| **check** | `print(fig.audit())` — do this before exporting |
| export | `fig.save("f.svg" / "f.png" / "f.pdf" / "f.html")` |

---

## 3. Placement

```python
el.at(x, y, anchor="nw")        # anchor may be any anchor name
el.at((x, y))                   # a point/anchor works too
el.center_at(x, y)
el.move(dx, dy)
el.set_x(120); el.set_y(40)

el.right_of(other, gap=24, align="center")   # align: top | center | bottom | None
el.left_of(other,  gap=24, align="top")
el.below_of(other, gap=12, align="left")     # align: left | center | right | None
el.above_of(other, gap=12)
el.next_to(other, side="right", gap=10)

el.inside(other, anchor="nw", pad=10)        # place within another element
el.align_to(other, "center_x")               # left|right|top|bottom|center_x|center_y|center
el.span_x(a, b, pad=8)                       # stretch to cover a..b horizontally
el.resize(w=200, h=60, anchor="center")      # anchor stays put
el.grow(dw=10, dh=0)
el.rotate(-90); el.scale_by(1.5); el.flip_h()
```

`align=None` leaves the cross axis untouched — useful when you already set it.

**Two axes, one call each.** `right_of` sets x (and the cross axis via
`align`); `below_of` sets y. Chaining both re-sets *both* axes, which is
usually not what you want:

```python
box.right_of(a, gap=40).above_of(a, gap=8)   # the second call moves x too!
box.right_of(a, gap=40, dy=-30)              # do this instead
box.right_of(a, gap=40).center_at(None, ROW) # or pin one axis explicitly
```

For figures with rows/columns, capture the lane coordinates once and reuse
them — it is far more robust than long chains:

```python
TOP, BOT = mesh_a.bbox.cy, mesh_b.bbox.cy
solver.right_of(feat, gap=60).center_at(None, TOP)
pmap.right_of(feat, gap=60).center_at(None, BOT)
```

---

## 4. Anchors

Every element exposes `n s e w ne nw se sw center` plus:

```python
el.at_angle(35)      # point on the border along a ray from the centre (0 = east, cw)
el.uv(0.25, 1.0)     # fractional position inside the bounding box
el.e + (6, -2)       # offset anchor (still live)
el.bbox              # BBox(x, y, w, h) with .x0 .x1 .cx .cy .center .corners
el.width / el.height / el.x / el.y
```

Anchors carry an outward **normal**, which is what makes `elbow` and `curve`
leave a box sensibly. Passing a whole *element* as a connector endpoint
(`arrow(a, b)`) picks the border point facing the other end automatically.

Connectors expose live anchors along their own path, so you can hang things
off an arrow and they keep up when its endpoints move:

```python
link = arrow(a.e, b.w)
Box("gate").center_at(link.mid)          # live: follows the arrow
arrow(note.s, link.anchor_at(0.25))
```

---

## 5. Elements

**Shapes** — all take an optional first `text` argument and auto-size to it:
`Box` (`Rect`), `Pill`/`Stadium`, `Ellipse`, `Circle(r=...)`, `Diamond`,
`Triangle`, `Hexagon`, `Parallelogram`, `Chevron`, `Star`, `Cylinder`, `Note`,
`Callout(text, target=point)`.

Common kwargs: `w, h, min_w, min_h, max_w, padding, wrap, align, valign,
radius, fill, stroke, stroke_width, stroke_dash, opacity, shadow, rotate, z,
name, style, theme`.

**Geometry** — `Line(a, b)`, `Polyline(points)`, `Polygon(points)`,
`Path("M0 0 L10 10 …")`, `Dot(center, r)`, `Marker(center, size, "diamond")`.
`Line`/`Polyline`/`Polygon` accept **live anchors** as points, so they track
whatever they were built from.

**Content** — `Text`, `Label`, `Image(path_or_bytes, w=...)`.

**Composites** — `Matrix(values, cell=16, cmap="viridis")`,
`LabelledMatrix(values, row_label=…, col_label=…, caption=…, brackets="round")`,
`Vector(values, orient="v")`, `ColorBar`, `Table(rows, header=True)`,
`Legend([(label, colour), …])`, `Brace(a, b, depth=12, label=...)`,
`Bracket`, `Panel(targets, pad, label)`, `Spacer(w, h)`, `Group(*children)`.

`Matrix` builds real cell elements: `m.cell(i, j)` is a `Box` you can anchor
to (`arrow(x.e, m.cell(0, 2).w)`) or restyle (`m.highlight(1, 1, stroke="red")`).
Paint kwargs passed to `Matrix(...)` style the **cells**.

---

## 6. Text and LaTeX

```python
Text("two\nlines", align="center", valign="center")
Text("wrapped prose …", wrap=260, line_height=1.4)
Text("plain **bold** and *italic*", markup=True)     # opt-in markdown-lite
Box("$C_{\\mathcal{MN}} = \\phi^{\\dagger}\\Pi\\phi$")   # inline math anywhere
```

**Spans** style part of a line. Pass a list wherever text is accepted —
including a `Box` label:

```python
Text(["accuracy ", Span("76.1", strike=True, color="@muted"), " → ",
      Span("94.6", color="@good", bold=True)])
Box(["status: ", Span("FAILED", color="#fff", bold=True)], fill="@bad")
```

`Span(text, color=, bold=, italic=, weight=, style=, size=, family=,
strike=, underline=)` — anything left unset is inherited. Strike-through and
underline are drawn as geometry, so they survive rasterising and outlining
(`text-decoration` does not).

* `$...$` spans are typeset with matplotlib's mathtext and emitted as **vector
  outlines**, so exported files never depend on installed fonts. Escape a
  literal dollar as `\$`.
* Use raw strings or double backslashes for TeX.
* `set_math_fontset("cm" | "stix" | "dejavusans")` changes the math font.
* Real LaTeX (`\begin{aligned}`, custom packages) is available when `latex` and
  `dvisvgm` are installed: `Text("...", math_backend="latex")`, configured via
  `set_latex_preamble(...)`. Check with `latex_available()`.
* `measure_text("hi", "sans-serif", 14)` returns the width in px if you need to
  size something yourself. Measurement uses glyph advances (no kerning), so it
  is accurate to roughly ±1%.

Text inside a `Box` is centred **optically** (on the cap-height band), which is
what looks right for short labels.

---

## 7. Connectors

```python
arrow(a.e, b.w)                                  # straight
line(a.e, b.w)                                   # no head
elbow(a.e, b.w, stub=14, corner=6)               # orthogonal -| routing
curve(a.s, b.s, bend=0.4)                        # smooth
connect(a, b, route="arc")                       # straight | elbow | curve | arc
double_arrow(a.e, b.w)
arrow(a.e, b.w, waypoints=[(120, 40)], corner=8) # explicit routing
```

Key kwargs: `head`/`tail` (`triangle`, `stealth`, `open`, `circle`, `diamond`,
`square`, `bar`, `cross`, `none`), `head_size`, `gap`/`start_gap`/`end_gap`
(pull the ends back), `start_side`/`end_side` (force an edge),
`label`, `label_pos` (0..1 along the path), `label_offset`, `label_side`
(`auto`/`above`/`below`/`center`), `label_rotate` (align the label to the
path), `label_bg`, plus any paint property (`stroke`, `stroke_width`,
`stroke_dash`, `opacity`).

On connectors and other line-like elements (`Line`, `Polyline`, `Path`,
`Brace`) there is no geometric width, so **`width=` means stroke width** —
`curve(src.s, dst.n, opacity=w, width=0.3 + 2 * w)` does what it looks like.

`bend` deepens the bow **along the anchors' facing direction** — `curve(a.s,
b.s, bend=0.5)` dips below both boxes. For plain points there is no normal to
follow so it bows sideways. `bow=` always pushes sideways (positive = left of
travel). Both are symmetric, and `bend` acts as a *floor* on the curve's
natural reach, so small values often change nothing.

For real control, place either end's Bezier handle yourself — the "whisker" a
vector editor lets you drag:

```python
curve(a.e, b.w, start_handle=0.6)                # leaves east on a long handle
curve(a.e, b.w, start_handle=0.8, end_handle=0.15)   # asymmetric
curve(a.e, b.w, start_handle=(0.5, -40))         # turned 40 deg off the face
curve(a.e, b.w, start_handle=Handle(px=60))      # absolute reach
```

The handle's **direction** is the asymptote — which way the curve insists on
leaving — and its **length** is how long it clings to it. Length is a fraction
of the straight-line distance between the endpoints, so the curve keeps its
shape when the things it connects move apart; `Handle(px=...)` opts out of
that. Angles are degrees off the face you attached to, positive clockwise on
screen. An end you give a handle ignores `bend` and `bow`.

Handles work with `waypoints=` too, and `tension=` (default 0.5) loosens the
spline that threads them.

`self_loop(element, side="top", size=36, label="retry")` draws an arrow that
leaves an element and returns to it — the staple of state machines.

Useful readouts: `c.point_at(t)`, `c.direction_at(t)`, `c.mid`, `c.length`.

Data-driven edges are just a loop:

```python
for src, dst, weight in edges:
    curve(src.s, dst.n, opacity=0.1 + 0.8 * weight,
          stroke_width=0.3 + 2 * weight, head="none")
```

---

## 8. Reusable components

A function returning a `Group` is a fine component. Subclass `Component` when
callers should be able to point at named parts of it:

```python
class Stage(Component):
    def build(self, title, w=150):          # group kwargs never reach build()
        body = Box(title, w=w, style="block")
        self.expose("body", body)
        self.expose("out", Dot(body.e, r=4).center)
        return [body]

a = Stage("Encode")
b = Stage("Solve", name="solver").right_of(a, gap=60)
arrow(a.out, b.body.w)                       # exposed anchors are live
```

`expose(name, anchor_or_element_or_callable)`; read them as attributes or via
`component.anchor(name)`. A `Component` is an ordinary `Group`, so it places,
moves and audits like anything else.

## 9. Layout helpers

```python
align([a, b, c], "top", to=None)         # top|bottom|left|right|center_x|center_y|center
distribute_h(items, gap=20, start=None)  # sequential, fixed gap
spread_h(items, x0, x1, mode="edges")    # even gaps across a span ("centers" also)
hstack(items, gap=16, align="center")    # -> Group
vstack(items, gap=12, align="left")      # -> Group
grid(items, cols=3, gap=(20, 14), align="nw")
fit(a, b, pad=20, label="stage", label_pos="nw")   # -> Group; .panel is the box
frame_around(items, pad=12)              # just the tracking box
brace_around(items, side="top", gap=8, label="stage")
same_width(items); same_height(items); same_size(items)
center_on(el, target); between(a, b, t=0.5); shift(items, dx, dy)
circular(items, center=(0,0), radius=140)
bbox_of([a, b, c])                       # read-only union
```

`fit()` returns a `Group` containing a `Panel` (drawn behind, `z=-1000`) plus
the items, so the whole cluster moves as one. The panel keeps tracking its
targets, so it re-fits if they move later.

---

## 10. Styling and themes

Resolution order for any property, innermost first:

1. keyword on the element — `Box("x", fill="red")`
2. the element's `style=` when given a `Style`/dict
3. its **classes**, last one winning — `Box("x", classes="block accent")`
4. inherited text properties from enclosing groups (font, colour, alignment)
5. themes on the element / its ancestors: **role override**, then **base token**
6. the default theme, then a hard-coded fallback

**Classes** are named styles defined by the theme, applied CSS-style:

```python
Box("solver", classes="stage accent")   # or style="stage accent"
box.add_class("highlight"); box.remove_class("accent")
```

They resolve *lazily* against the live theme chain, so the same class can mean
different things inside a differently themed group. An unknown class is a
warning at render time, not an error. `.name` with a leading dot also works.

```python
T = PAPER.derive(                        # or Theme(...), or DEFAULT_THEME.derive(...)
    font_size=13, radius=4,              # base tokens: apply to every role
    palette={"brand": "#3B6EA5"},        # referenced as "@brand"
    box=Style(fill="#fff", stroke="#222", padding=(9, 13)),   # role overrides
    arrow=Style(stroke="#222", head_size=8),
    styles={"solver": Style(fill="@brand", stroke="#1b1b1b")},  # classes
)

with Figure(theme=T) as fig:
    Box("FMap Solver", style="solver")   # named style
    Box("plain", fill="@brand")          # palette token
```

Roles: `box`, `text`, `label`, `ellipse`, `path`, `line`, `arrow`, `panel`,
`group`, `image`, `matrix`, `brace`, `axis`, `grid`, `marker`.

Property aliases are accepted everywhere: `bg`/`background` → `fill`,
`border`/`border_color` → `stroke`, `lw`/`border_width` → `stroke_width`,
`dash` → `stroke_dash`, `corner_radius` → `radius`, `text_color`/`fg` →
`color`, `font`/`family` → `font_family`, `align` → `text_align`,
`alpha` → `opacity`. Flags: `bold=True`, `italic=True`, `monospace=True`.

Dash presets: `"solid" "dashed" "dotted" "dashdot"`, or `[6, 4]`, or `True`.

Built-in themes: `DEFAULT_THEME`, `PAPER`, `SLIDE`, `DARK`, `BLUEPRINT`,
`MINIMAL`, `SOFT` — also `get_theme("paper")`. Built-in named styles present in
every theme: `block`, `blue`, `green`, `warm`, `slate`, `ghost`, `plain`,
`card`.

Extras: `shadow=True` or `shadow={"dy": 2, "blur": 6, "opacity": 0.15}` (an
SVG filter — see gotcha 11);
gradients via `fill={"type": "linear", "stops": ["#fff", "#333"], "angle": 90}`.

Colour helpers: `mix, lighten, darken, alpha, saturate, contrast_color,
colormap("viridis", t), palette("figkit", n), to_hex`.

---

## 11. Data-driven graphics

```python
fr = Frame(w=430, h=240, xlim=(0, 50), ylim=(0.35, 1.0))   # a Group + a mapping
fr.at(0, 60)                       # move it like any element

fr.pt(x, y)      # data -> world Point;   fr.px(x) / fr.py(y) for one axis
fr.data(px, py)  # world -> data

fr.gridlines(n=6)
fr.xaxis(n=6, title="epoch")
fr.yaxis(n=5, title="accuracy", fmt=lambda v: f"{v:.0%}")
fr.axes(xlabel="x", ylabel="y", grid=True)       # both at once

fr.line(xs, ys, stroke="@primary", lw=2, smooth=False)
fr.scatter(xs, ys, size=7, values=weights, cmap="viridis")
fr.bars(xs, heights, width=0.7)
fr.area_fill(xs, ys, base=0)
fr.region(x0, x1, y0, y1, fill="#4C72B0", fill_opacity=0.1)
fr.hline(0.5); fr.vline(10)
fr.text("warm-up", 4, 0.96)
fr.at_data(some_box, x=6, y=0.8, anchor="s")
```

Everything returned is an ordinary element, so you can annotate it:
`arrow(note.se, Dot(fr.pt(50, 0.94)).nw)`. Also `xscale="log"`,
`autoscale(xs, ys)`, `nice_ticks(lo, hi, n)`, and `clip_data=True` to clip
marks to the plot area.

---

## 12. Images

```python
Image("logo.svg", w=80)        # SVGs are inlined as vectors (ids namespaced)
Image("plot.png", w=200)       # rasters are base64-embedded; aspect preserved
Image(raw_bytes, mime="image/png")
Image("photo.jpg", w=200, h=120, fit="cover")   # contain | cover | fill
```

Pass only `w` **or** `h` to keep the aspect ratio. `im.natural_size` gives the
source dimensions.

---

## 13. Export

```python
fig.save("f.svg")                     # native, self-contained
fig.save("f.png", scale=2)            # or dpi=300
fig.save("f.pdf")
fig.save("f.html")                    # standalone responsive page
fig.to_svg(text_as_paths=True)        # outline text: no font dependency
fig.to_svg(embed_fonts=True)          # or embed the font as base64 @font-face
svg_string = fig.to_svg()
available_backends()                  # what this machine can rasterise with
```

PNG/PDF need a converter: `pip install "figkit[export]"` (cairosvg), or
`rsvg-convert` / `resvg` / `inkscape` / headless chromium on `PATH`.
PNG and PDF outline text automatically, so they always match the SVG.

Install: `pip install figkit` · `figkit[latex]` (math) · `figkit[export]`
(PNG/PDF) · `figkit[all]`.

---

## 14. Checking your work: `fig.audit()`

```python
report = fig.audit()
print(report)                # one line per problem, or "no issues"
if report: ...               # falsy when the figure is clean
report.raise_if_any()        # turn it into an assertion, for tests
report.by_kind("overlap")    # the raw findings, for programmatic use
```

Each finding has `.kind`, `.message`, `.severity` (`error`/`warning`),
`.where` (a point to look at) and `.elements`. The checks:

| kind | what it means |
|---|---|
| `overlap` | two elements collide, or one is painted over something it hides |
| `overflow` | a label sticks out of the shape it belongs to |
| `contrast` | text is too close in luminance to what is behind it |
| `crossing` | a connector passes through an element it does not connect |
| `degenerate` | a zero-size shape or a zero-length arrow |
| `offscreen` | content outside a pinned canvas (auto-sized figures cannot have any) |

**It is built to stay quiet about deliberate overlap**, so a clean report is
meaningful. It already knows that labels sit inside boxes, that panels sit
behind their contents, that arrows touch the things they connect, that
adjacent matrix cells share edges, and that anything with `z < 0` is a
backdrop. Decorative shapes drawn together under one group may overlap freely.

When it flags something you meant, say so in the code:

```python
arrow(spine_bottom, spine_top).ignore_audit()   # runs behind the nodes on purpose
Box("watermark", audit=False)
fig.audit(ignore=[element])                     # or skip specific elements
fig.audit(crossing=False, contrast=False)       # or switch off a whole check
fig.audit(overlap="all")                        # stricter: every partial overlap
fig.audit(min_contrast=4.5)                     # WCAG AA for body text
```

## 15. Gotchas

1. **`Group` takes ownership.** `Group(a, b)` and `fit(a, b)` *reparent* their
   children. To only read a combined bounding box, use `bbox_of([a, b])`.
2. **Elements auto-add inside `with Figure()`.** Helper functions that create
   elements also add them, including ones you then wrap in a `Group` — that is
   fine (the group steals them), but a group created with `add=False` inside a
   figure is *not* drawn.
3. **Nested groups paint as a unit.** A filled `Panel` inside a group drawn
   later covers everything painted earlier, even elements with lower `z`.
   `z` only sorts within one parent.
4. **Connectors are not in your groups by default.** If you move a cluster by
   grouping it, include the arrows: `fit(row, *wires, pad=18)`.
5. **Don't `resize()` a `Group`** unless you want to *scale* it — it applies a
   transform and stretches text. Size the children instead.
6. **Chaining `right_of().below_of()` sets both axes twice.** Use `dx`/`dy`, or
   pin one axis with `center_at(None, y)`.
7. **`fit`/`Panel` keep tracking.** They re-fit when their targets move, so
   place the contents before you rely on the panel's own bbox.
8. **Very light `Matrix` cells vanish on white.** Pass `stroke="#333"` (paint
   kwargs on `Matrix` go to the cells).
9. **Set the theme on the `Figure`,** not after creating elements — sizes are
   measured with the theme's font.
10. **8-digit hex and `rgba()` work** and are split into `fill` +
    `fill-opacity` on output, so rasterisers handle them correctly.
11. **A viewer without your font can make words collide** in plain SVG:
    positions are absolute, so a wider substitute overflows them. Export with
    `embed_fonts=True`, or `text_as_paths=True` (what PNG/PDF already do).
12. **`shadow=` is an SVG filter, and cairosvg ignores filters.** It shows in
    SVG and HTML but not in a cairosvg-rendered PNG/PDF; figkit warns when
    that happens. Use `rsvg-convert`/`resvg`/chromium, or skip shadows for
    figures headed to PNG.

---

## 16. Worked pattern

```python
from figkit import *

T = PAPER.derive(font_size=13,
                 styles={"stage": Style(fill="#eef3f9", stroke="#3B6EA5")})

with Figure(theme=T, pad=26, background="#ffffff") as fig:
    # 1. lay out the backbone, capturing lane coordinates
    inp = Box("input\n$x$", style="block", w=110)
    ROW = inp.bbox.cy

    enc = Box("Encoder", style="stage", w=150).right_of(inp, gap=54)
    lat = Vector([0.9, 0.3, 0.6, 0.1], cell=(44, 12), cmap="grays",
                 stroke="#333", stroke_width=0.7).right_of(enc, gap=40)
    lat.center_at(None, ROW)
    z_lab = Text("$z$", font_size=14).below_of(lat, gap=8)

    dec = Box("Decoder", style="stage", w=150).right_of(lat, gap=40)
    out = Box("output\n$\\hat{x}$", style="block", w=110).right_of(dec, gap=54)

    # 2. wire it up — anchors stay glued to the boxes
    arrow(inp.e, enc.w); arrow(enc.e, lat.w)
    arrow(lat.e, dec.w); arrow(dec.e, out.w)

    # 3. group and annotate
    body = fit(enc, lat, z_lab, dec, pad=20, label="autoencoder",
               label_pos="below", style="ghost")
    loss = curve(out.s, inp.s, bend=0.45, label="reconstruction loss",
                 label_side="below", stroke="@accent", stroke_dash="dashed")

    Text("Figure 1: the model.", font_size=11, color="@muted", align="left") \
        .below_of(loss, gap=18).align_to(inp, "left")

print(fig.audit())            # catches overlaps, overflow, unreadable text
fig.save("figure.svg")
fig.save("figure.png", scale=2)
```

**Workflow:** build, then `print(fig.audit())` after each structural change.
A clean report means no element is covering another, no label has escaped its
box and no text is unreadable — the mistakes that are obvious in a picture and
invisible in the code. Export and look at the PNG for the things the audit
cannot judge: whether the composition actually reads well.
