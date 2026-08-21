"""Text layout: multi-line, inline ``$math$``, wrapping and optical centring."""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field

from .core import Element
from .fonts import get_font, measure_text
from .geom import BBox
from .mathtext import MathError, math_available, render_math
from .style import normalize_dash
from .svgdoc import Node, RenderContext
from .svgpath import translate_path_data

__all__ = ["Text", "Label", "Span", "TextLayout", "layout_text",
           "measure_block"]

# ``$...$`` with support for escaped ``\$``
_MATH_RE = re.compile(r"(?<!\\)\$(.+?)(?<!\\)\$", re.S)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.S)


@dataclass(frozen=True)
class Span:
    """A styled piece of a :class:`Text`.

    >>> Text(["the model ", Span("fails", color="@bad", strike=True), " here"])

    Anything left as ``None`` is inherited from the ``Text`` it belongs to.
    """

    text: str
    color: str = None
    bold: bool = None
    italic: bool = None
    weight: str = None
    style: str = None
    size: float = None
    family: str = None
    strike: bool = False
    underline: bool = False

    def overrides(self) -> dict:
        """The properties this span changes, as a plain dict."""
        out = {}
        if self.color is not None:
            out["color"] = self.color
        if self.weight is not None:
            out["weight"] = self.weight
        elif self.bold is not None:
            out["weight"] = "bold" if self.bold else "normal"
        if self.style is not None:
            out["style"] = self.style
        elif self.italic is not None:
            out["style"] = "italic" if self.italic else "normal"
        if self.size is not None:
            out["size"] = float(self.size)
        if self.family is not None:
            out["family"] = self.family
        decoration = tuple(d for d, on in (("strike", self.strike),
                                           ("underline", self.underline)) if on)
        if decoration:
            out["decoration"] = decoration
        return out


@dataclass
class Run:
    """One measured piece of a line: plain text or a math expression."""

    kind: str            # "text" | "math"
    content: str
    width: float = 0.0
    ascent: float = 0.0
    descent: float = 0.0
    x: float = 0.0
    font_size: float = 12.0
    weight: str = "normal"
    style: str = "normal"
    math: object = None
    color: str = None
    family: object = None
    decoration: tuple = ()

    @property
    def key(self) -> tuple:
        """What must match for two runs to be merged into one SVG node."""
        return (self.kind, self.weight, self.style, self.font_size,
                self.color, self.family, self.decoration)


@dataclass
class Line:
    runs: list = field(default_factory=list)
    width: float = 0.0
    ascent: float = 0.0
    descent: float = 0.0
    baseline: float = 0.0   # relative to the top of the block


@dataclass
class TextLayout:
    """The measured result of laying out a string."""

    lines: list = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    cap_top: float = 0.0      # top of the cap-height band (optical centring)
    baseline_last: float = 0.0

    @property
    def optical_height(self) -> float:
        return max(0.0, self.baseline_last - self.cap_top)


def _split_math(text: str) -> list:
    """Split a string into alternating text / math pieces."""
    out = []
    pos = 0
    for m in _MATH_RE.finditer(text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()]))
        out.append(("math", m.group(1)))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:]))
    if not out:
        out = [("text", text)]
    return [(k, v.replace("\\$", "$") if k == "text" else v) for k, v in out]


def _apply_markup(piece: str, weight: str, style: str) -> list:
    """Expand ``**bold**`` / ``*italic*`` into styled sub-runs."""
    out = []
    pos = 0
    tokens = []
    for m in _BOLD_RE.finditer(piece):
        tokens.append((m.start(), m.end(), m.group(1), "bold", None))
    for m in _ITALIC_RE.finditer(piece):
        if any(s <= m.start() < e for s, e, *_ in tokens):
            continue
        tokens.append((m.start(), m.end(), m.group(1), None, "italic"))
    tokens.sort()
    for start, end, body, w, s in tokens:
        if start > pos:
            out.append((piece[pos:start], weight, style))
        out.append((body, w or weight, s or style))
        pos = end
    if pos < len(piece):
        out.append((piece[pos:], weight, style))
    return out or [(piece, weight, style)]


def _as_pieces(content, base: dict) -> list:
    """Flatten ``str`` / :class:`Span` / lists into ``[(text, overrides)]``."""
    if content is None:
        return [("", dict(base))]
    if isinstance(content, Span):
        return [(str(content.text), {**base, **content.overrides()})]
    if isinstance(content, str):
        return [(content, dict(base))]
    if isinstance(content, (list, tuple)):
        out = []
        for item in content:
            out.extend(_as_pieces(item, base))
        return out
    return [(str(content), dict(base))]


def _split_lines(pieces: list) -> list:
    """Break styled pieces on newlines, keeping each piece's styling."""
    lines = [[]]
    for text, overrides in pieces:
        parts = str(text).split("\n")
        for i, part in enumerate(parts):
            if i:
                lines.append([])
            if part:
                lines[-1].append((part, overrides))
    return lines


def layout_text(text, font_family=None, font_size: float = 14.0,
                weight="normal", style="normal", line_height: float = 1.3,
                letter_spacing: float = 0.0, max_width: float = None,
                math_backend: str = "auto", math_scale: float = 1.0,
                markup: bool = False, color=None) -> TextLayout:
    """Measure ``text``, returning line boxes, run positions and baselines.

    ``text`` may be a string, a :class:`Span`, or a list mixing the two.
    """
    base = {"weight": weight, "style": style, "size": float(font_size),
            "family": font_family, "color": color, "decoration": ()}
    metrics = get_font(font_family, weight, style).metrics

    lines: list = []
    for styled_line in _split_lines(_as_pieces(text, base)):
        runs: list = []
        for body, ov in styled_line:
            runs.extend(_build_runs(body, ov, markup, math_backend,
                                    math_scale, letter_spacing))
        if max_width and max_width > 0:
            lines.extend(_wrap(runs, max_width, letter_spacing))
        else:
            lines.append(runs)

    out_lines: list = []
    default_asc = metrics.ascent * font_size
    default_desc = metrics.descent * font_size
    for runs in lines:
        x = 0.0
        for r in runs:
            r.x = x
            x += r.width
        asc = max([r.ascent for r in runs] + [default_asc])
        desc = max([r.descent for r in runs] + [default_desc])
        out_lines.append(Line(runs=runs, width=x, ascent=asc, descent=desc))

    leading = font_size * line_height
    y = 0.0
    max_w = 0.0
    for ln in out_lines:
        box = max(leading, ln.ascent + ln.descent)
        extra = max(0.0, box - (ln.ascent + ln.descent))
        ln.baseline = y + extra / 2.0 + ln.ascent
        y += box
        max_w = max(max_w, ln.width)

    # The cap band (first cap-height down to the last baseline) is what we
    # centre on: it is what the eye reads as the extent of a short label.
    cap = (metrics.cap_height or 0.7) * font_size
    first = out_lines[0] if out_lines else Line(baseline=cap)
    last = out_lines[-1] if out_lines else first
    top_reach = cap
    if first.runs and any(r.kind == "math" for r in first.runs):
        top_reach = max(cap, first.ascent)
    return TextLayout(lines=out_lines, width=max_w, height=y,
                      cap_top=first.baseline - top_reach,
                      baseline_last=last.baseline)


def _build_runs(body: str, ov: dict, markup: bool, math_backend: str,
                math_scale: float, letter_spacing: float) -> list:
    """Turn one styled string into measured runs, expanding $math$ and markup."""
    size = ov["size"]
    runs: list = []
    for kind, content in _split_math(body):
        if kind == "math":
            if not content.strip():
                continue
            try:
                mr = render_math(content, size * math_scale, math_backend)
            except MathError:
                # A genuine TeX error is the caller's problem, but simply not
                # having the optional dependency should not blow up a whole
                # figure — set the source in italics and say what is missing.
                if math_available():
                    raise
                warnings.warn(
                    "figkit: $math$ needs matplotlib; the expression was set "
                    "as plain text instead. Install it with "
                    "pip install 'figkit[latex]'.", stacklevel=4)
                runs.append(_text_run(content, ov, ov["weight"], "italic",
                                      letter_spacing))
                continue
            runs.append(Run("math", content, mr.width, mr.ascent, mr.descent,
                            font_size=size, math=mr, color=ov.get("color"),
                            decoration=ov.get("decoration", ())))
            continue
        if content == "":
            continue
        sub = (_apply_markup(content, ov["weight"], ov["style"]) if markup
               else [(content, ov["weight"], ov["style"])])
        for part, w, st in sub:
            if part == "":
                continue
            runs.append(_text_run(part, ov, w, st, letter_spacing))
    return runs


def _text_run(part: str, ov: dict, weight, style, letter_spacing: float) -> Run:
    size = ov["size"]
    family = ov.get("family")
    width = measure_text(part, _fam(family), size, weight, style, letter_spacing)
    metrics = get_font(family, weight, style).metrics
    return Run("text", part, width, metrics.ascent * size,
               metrics.descent * size, font_size=size, weight=weight,
               style=style, color=ov.get("color"), family=family,
               decoration=ov.get("decoration", ()))


def _merge_runs(runs: list) -> list:
    """Join neighbouring text runs that share styling.

    Emitting one ``<text>`` per *word* would pin each word to an absolute x —
    exact, but if the viewer lacks the declared font the substitute's wider
    glyphs collide. One ``<text>`` per phrase lets the renderer space the words
    itself, so a substituted font degrades gracefully instead.
    """
    out: list = []
    for run in runs:
        prev = out[-1] if out else None
        if (prev is not None and prev.kind == "text" and run.kind == "text"
                and prev.key == run.key
                and abs((prev.x + prev.width) - run.x) < 0.01):
            out[-1] = Run("text", prev.content + run.content,
                          prev.width + run.width, max(prev.ascent, run.ascent),
                          max(prev.descent, run.descent), prev.x,
                          prev.font_size, prev.weight, prev.style,
                          color=prev.color, family=prev.family,
                          decoration=prev.decoration)
        else:
            out.append(run)
    return out


def _decoration_nodes(run, x: float, baseline: float, color, alpha) -> list:
    """Draw strike-through / underline as geometry.

    ``text-decoration`` is widely ignored by SVG rasterisers and disappears
    entirely once text is outlined, so figkit draws the rules itself.
    """
    if not run.decoration:
        return []
    size = run.font_size or 12.0
    thickness = max(0.8, size * 0.055)
    out = []
    for kind in run.decoration:
        if kind == "strike":
            y = baseline - size * 0.28
        elif kind == "underline":
            y = baseline + size * 0.12
        else:
            continue
        out.append(Node("rect", x=x, y=y - thickness / 2.0, width=run.width,
                        height=thickness, fill=color, fill_opacity=alpha,
                        stroke="none"))
    return out


def _norm_content(value):
    """Accept a string, a Span, or a list of them."""
    if value is None:
        return ""
    if isinstance(value, (str, Span, list, tuple)):
        return value
    return str(value)


def plain_text(content) -> str:
    """The text of a span tree, with styling dropped."""
    if content is None:
        return ""
    if isinstance(content, Span):
        return str(content.text)
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        return "".join(plain_text(item) for item in content)
    return str(content)


def _fam(font_family):
    if font_family is None:
        return None
    return font_family if isinstance(font_family, str) else ", ".join(font_family)


def _wrap(runs: list, max_width: float, letter_spacing: float) -> list:
    """Greedy word wrap. Math runs are unbreakable atoms; every run keeps its
    own styling, so a wrapped line can still mix spans."""
    lines: list = []
    cur: list = []
    cur_w = 0.0

    def flush():
        nonlocal cur, cur_w
        if cur:
            while cur and cur[-1].kind == "text" and cur[-1].content.strip() == "":
                cur.pop()
            lines.append(cur)
        cur = []
        cur_w = 0.0

    def clone(run: Run, content: str, width: float) -> Run:
        return Run(run.kind, content, width, run.ascent, run.descent,
                   font_size=run.font_size, weight=run.weight, style=run.style,
                   math=run.math, color=run.color, family=run.family,
                   decoration=run.decoration)

    for run in runs:
        if run.kind == "math":
            if cur_w + run.width > max_width and cur:
                flush()
            cur.append(clone(run, run.content, run.width))
            cur_w += run.width
            continue
        for word in re.split(r"(\s+)", run.content):
            if word == "":
                continue
            w = measure_text(word, _fam(run.family), run.font_size, run.weight,
                             run.style, letter_spacing)
            if word.strip() == "":
                if cur:
                    cur.append(clone(run, word, w))
                    cur_w += w
                continue
            if cur_w + w > max_width and cur:
                flush()
            cur.append(clone(run, word, w))
            cur_w += w
    flush()
    return lines or [[]]


def measure_block(text: str, **kw) -> tuple:
    """``(width, height)`` of a text block — handy for sizing things by hand."""
    lay = layout_text(text, **kw)
    return lay.width, lay.height


# ==========================================================================
# Text element
# ==========================================================================

class Text(Element):
    """A block of text. Supports ``\\n``, inline ``$math$`` and wrapping.

    >>> Text("Feature\\nExtractor", bold=True, font_size=16)
    >>> Text("loss $L_{\\\\mathrm{fmap}}$", color="#333")
    """

    role = "text"
    ANCHOR_MAP = {"left": "start", "start": "start", "center": "middle",
                  "middle": "middle", "right": "end", "end": "end"}

    def __init__(self, text="", x: float = 0.0, y: float = 0.0, *,
                 width: float = None, wrap: float = None, markup: bool = False,
                 rotate: float = None, **kw):
        self._text = _norm_content(text)
        self._wrap = wrap if wrap is not None else width
        self._markup = markup
        self._layout: TextLayout | None = None
        super().__init__(x, y, None, None, **kw)
        if self._wrap:
            self._explicit_w = False
        if rotate:
            self.rotate(rotate)

    # -- content ---------------------------------------------------------
    @property
    def text(self) -> str:
        """The plain-text content, with any span styling flattened away."""
        return plain_text(self._text)

    @property
    def content(self):
        """The content as given: a string, a :class:`Span`, or a list."""
        return self._text

    @text.setter
    def text(self, value) -> None:
        self._text = _norm_content(value)
        self.invalidate()

    def set_text(self, value: str) -> "Text":
        self.text = value
        return self

    def wrap_at(self, width: float) -> "Text":
        self._wrap = width
        return self.invalidate()

    # -- measurement -----------------------------------------------------
    def _layout_kwargs(self) -> dict:
        return dict(
            font_family=self.prop("font_family"),
            font_size=float(self.prop("font_size")),
            weight=self.prop("font_weight"),
            style=self.prop("font_style"),
            line_height=float(self.prop("line_height")),
            letter_spacing=float(self.prop("letter_spacing", 0) or 0),
            max_width=self._wrap,
            math_backend=self.prop("math_backend", "auto"),
            math_scale=float(self.prop("math_scale", 1.0) or 1.0),
            markup=self._markup,
            color=self.prop("color"),
        )

    @property
    def layout(self) -> TextLayout:
        self._ensure()
        return self._layout

    def _measure(self) -> None:
        self._layout = layout_text(self._text, **self._layout_kwargs())
        self._w = self._wrap if self._wrap else self._layout.width
        self._h = self._layout.height

    @property
    def optical_bbox(self) -> BBox:
        """Cap-height band — what you want to centre inside a box."""
        self._ensure()
        bb = self.bbox
        lay = self._layout
        if not lay.lines:
            return bb
        top = bb.y + lay.cap_top
        bottom = bb.y + lay.baseline_last
        return BBox(bb.x, top, bb.w, max(0.0, bottom - top))

    @property
    def first_baseline(self) -> float:
        self._ensure()
        return self.bbox.y + (self._layout.lines[0].baseline
                              if self._layout.lines else 0.0)

    # -- rendering -------------------------------------------------------
    def _render_content(self, ctx: RenderContext):
        self._ensure()
        lay = self._layout
        if not lay.lines:
            return None
        bb = self.local_bbox
        from .paint import _color as _split_color
        color, color_alpha = _split_color(self.prop("color"), ctx)
        if color is None:
            color, color_alpha = "#000000", None
        align = str(self.prop("text_align", "center")).lower()
        anchor = self.ANCHOR_MAP.get(align, "middle")
        family = self.prop("font_family")
        size = float(self.prop("font_size"))
        weight = self.prop("font_weight")
        fstyle = self.prop("font_style")
        spacing = float(self.prop("letter_spacing", 0) or 0)
        decoration = self.prop("text_decoration", None)
        stroke = self.prop("stroke", None)
        stroke_w = self.prop("stroke_width", 0)
        math_color = self.prop("math_color", None) or color
        as_paths = ctx.text_as_paths
        ctx.note_font(family, weight, fstyle)

        nodes: list = []
        for line in lay.lines:
            if not line.runs:
                continue
            runs = _merge_runs(line.runs)
            if anchor == "start":
                x0 = bb.x
            elif anchor == "end":
                x0 = bb.x + bb.w - line.width
            else:
                x0 = bb.x + (bb.w - line.width) / 2.0
            by = bb.y + line.baseline
            for run in runs:
                rx = x0 + run.x
                run_color, run_alpha = (_split_color(run.color, ctx)
                                        if run.color else (color, color_alpha))
                if run.kind == "math":
                    mr = run.math
                    if mr is None or mr.empty:
                        continue
                    d = translate_path_data(mr.d, rx, by)
                    nodes.append(Node("path", d=d,
                                      fill=run_color or math_color,
                                      fill_opacity=run_alpha,
                                      fill_rule=mr.fill_rule, stroke="none"))
                    nodes.extend(_decoration_nodes(run, rx, by, run_color,
                                                   run_alpha))
                    continue
                if not run.content.strip():
                    continue
                run_family = run.family if run.family is not None else family
                run_size = run.font_size or size
                if as_paths:
                    font = get_font(run_family, run.weight, run.style)
                    if font.available:
                        d = font.text_to_path(run.content, run_size, spacing)
                        if d:
                            nodes.append(Node("path",
                                              d=translate_path_data(d, rx, by),
                                              fill=run_color,
                                              fill_opacity=run_alpha,
                                              stroke="none"))
                            nodes.extend(_decoration_nodes(run, rx, by,
                                                           run_color, run_alpha))
                            continue
                    ctx.warn(f"text_as_paths: no outline font for {run_family!r}")
                attrs = dict(x=rx, y=by, fill=run_color, fill_opacity=run_alpha,
                             font_family=run_family, font_size=run_size)
                if str(run.weight) not in ("normal", "400"):
                    attrs["font_weight"] = run.weight
                if str(run.style) != "normal":
                    attrs["font_style"] = run.style
                if spacing:
                    attrs["letter_spacing"] = spacing
                if decoration:
                    attrs["text_decoration"] = decoration
                if stroke and stroke != "none" and stroke_w:
                    attrs["stroke"] = stroke
                    attrs["stroke_width"] = stroke_w
                    attrs["paint_order"] = "stroke"
                    dash = normalize_dash(self.prop("stroke_dash", None))
                    if dash:
                        attrs["stroke_dasharray"] = dash
                attrs["xml__space"] = ("preserve"
                                       if run.content != run.content.strip()
                                       else None)
                nodes.append(Node("text", text=run.content, **attrs))
                nodes.extend(_decoration_nodes(run, rx, by, run_color,
                                               run_alpha))
        return nodes or None

    def __repr__(self) -> str:
        preview = self._text if len(self._text) <= 24 else self._text[:21] + "..."
        return f"<Text {preview!r} {self.bbox}>"


class Label(Text):
    """Text with the ``label`` role — smaller by default, for annotations."""

    role = "label"
