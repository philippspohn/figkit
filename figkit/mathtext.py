"""LaTeX / math rendering to SVG paths.

Two backends:

``mathtext`` (default)
    Uses matplotlib's built-in TeX-subset renderer.  No LaTeX install needed,
    produces real vector outlines, handles the vast majority of inline math
    used in figures (``$F_{\\mathcal{M}}$``, ``\\sum``, ``\\frac``, ...).

``latex``
    Shells out to a real ``latex`` + ``dvisvgm`` toolchain, so anything your
    TeX distribution can typeset works (``\\begin{aligned}``, custom packages
    via ``preamble=``).  Requires those binaries on ``PATH``.

Both return glyph outlines, so exported figures never depend on fonts being
installed on the viewer's machine.
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

__all__ = ["MathRender", "render_math", "math_available", "latex_available",
           "set_math_fontset", "set_latex_preamble", "MathError"]


class MathError(RuntimeError):
    """Raised when a math expression cannot be typeset."""


@dataclass
class MathRender:
    """Vector result of typesetting a math expression.

    Coordinates are in px with the *baseline at y = 0* and y growing downward,
    so the outline can be dropped straight into an SVG at a baseline point.
    """

    d: str = ""
    width: float = 0.0
    ascent: float = 0.0          # above baseline, positive
    descent: float = 0.0         # below baseline, positive
    x_offset: float = 0.0
    size: float = 12.0
    backend: str = "mathtext"
    fill_rule: str = "nonzero"
    extra: dict = field(default_factory=dict)

    @property
    def height(self) -> float:
        return self.ascent + self.descent

    @property
    def empty(self) -> bool:
        return not self.d


_FONTSET = ["cm"]          # cm | dejavusans | dejavuserif | stix | stixsans
_PREAMBLE = [r"\usepackage{amsmath}\usepackage{amssymb}\usepackage{amsfonts}"]


def set_math_fontset(name: str) -> None:
    """Set the matplotlib mathtext font set (``cm``, ``stix``, ``dejavusans``...)."""
    _FONTSET[0] = name
    render_math.cache_clear()


def set_latex_preamble(preamble: str) -> None:
    """Set the LaTeX preamble used by the ``latex`` backend."""
    _PREAMBLE[0] = preamble
    render_math.cache_clear()


def math_available() -> bool:
    """True when the built-in ``mathtext`` backend can be used."""
    try:
        import matplotlib  # importing it is the availability check
        return matplotlib is not None
    except ImportError:
        return False


def latex_available() -> bool:
    """True when a real ``latex`` + ``dvisvgm`` toolchain is on PATH."""
    return bool(shutil.which("latex") and shutil.which("dvisvgm"))


# --------------------------------------------------------------------------
# matplotlib mathtext backend
# --------------------------------------------------------------------------

_MPL_CODES = {1: "M", 2: "L", 3: "Q", 4: "C", 79: "Z"}
_MPL_NARGS = {1: 1, 2: 1, 3: 2, 4: 3, 79: 1}


def _fmt(v: float) -> str:
    s = f"{v:.3f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _render_mathtext(expr: str, size: float) -> MathRender:
    try:
        import matplotlib
        from matplotlib.textpath import TextPath
        from matplotlib.font_manager import FontProperties
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise MathError(
            "math rendering needs matplotlib: pip install 'figkit[latex]'"
        ) from exc

    matplotlib.rcParams["mathtext.fontset"] = _FONTSET[0]
    body = expr if expr.startswith("$") else f"${expr}$"
    try:
        tp = TextPath((0, 0), body, size=size, prop=FontProperties(size=size))
    except Exception as exc:
        raise MathError(f"could not typeset {expr!r}: {exc}") from exc

    verts, codes = tp.vertices, tp.codes
    if codes is None or len(verts) == 0:
        return MathRender(size=size, backend="mathtext")

    parts = []
    i = 0
    n = len(codes)
    while i < n:
        code = int(codes[i])
        nargs = _MPL_NARGS.get(code, 1)
        letter = _MPL_CODES.get(code)
        if letter is None:
            i += nargs
            continue
        if letter == "Z":
            parts.append("Z")
        else:
            pts = verts[i:i + nargs]
            coords = " ".join(f"{_fmt(float(p[0]))} {_fmt(-float(p[1]))}"
                              for p in pts)
            parts.append(f"{letter}{coords}")
        i += nargs
    d = "".join(parts)

    bb = tp.get_extents()
    return MathRender(
        d=d,
        width=max(0.0, float(bb.x1 - bb.x0)),
        ascent=max(0.0, float(bb.y1)),
        descent=max(0.0, -float(bb.y0)),
        x_offset=float(bb.x0),
        size=size,
        backend="mathtext",
    )


# --------------------------------------------------------------------------
# real LaTeX backend (latex + dvisvgm)
# --------------------------------------------------------------------------

_TEX_DOC = r"""\documentclass[12pt]{article}
%(preamble)s
\pagestyle{empty}
\setlength{\parindent}{0pt}
\begin{document}
%(body)s
\end{document}
"""

_UNIT = {"pt": 1.0, "px": 1.0, "": 1.0, "mm": 72.0 / 25.4, "cm": 72.0 / 2.54,
         "in": 72.0, "pc": 12.0, "ex": 6.0, "em": 12.0}


def _len_pt(value: str) -> float:
    m = re.match(r"^\s*(-?[\d.]+)\s*([a-z%]*)\s*$", str(value or "0"))
    if not m:
        return 0.0
    return float(m.group(1)) * _UNIT.get(m.group(2), 1.0)


def _render_latex(expr: str, size: float, display: bool = False) -> MathRender:
    if not latex_available():
        raise MathError(
            "the 'latex' backend needs `latex` and `dvisvgm` on PATH; "
            "use backend='mathtext' (the default) instead"
        )
    body = expr.strip()
    if body.startswith("$") and body.endswith("$"):
        body = body[1:-1]
    if not re.match(r"^\s*\\begin\{", body) and "$" not in body:
        body = (f"\\[{body}\\]" if display else f"${body}$")
    tex = _TEX_DOC % {"preamble": _PREAMBLE[0], "body": body}

    with tempfile.TemporaryDirectory(prefix="figkit-tex-") as tmp:
        tex_path = os.path.join(tmp, "fig.tex")
        with open(tex_path, "w", encoding="utf-8") as fh:
            fh.write(tex)
        try:
            proc = subprocess.run(
                ["latex", "-interaction=nonstopmode", "-halt-on-error", "fig.tex"],
                cwd=tmp, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            raise MathError("latex timed out") from exc
        dvi = os.path.join(tmp, "fig.dvi")
        if not os.path.exists(dvi):
            log = (proc.stdout or "") + (proc.stderr or "")
            tail = "\n".join(log.strip().splitlines()[-15:])
            raise MathError(f"latex failed for {expr!r}:\n{tail}")
        try:
            subprocess.run(
                ["dvisvgm", "--no-fonts", "--exact-bbox", "--scale=1",
                 "-o", "fig.svg", "fig.dvi"],
                cwd=tmp, capture_output=True, text=True, timeout=60, check=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise MathError(f"dvisvgm failed for {expr!r}: {exc}") from exc
        with open(os.path.join(tmp, "fig.svg"), "r", encoding="utf-8") as fh:
            svg_text = fh.read()

    d, w, h = _flatten_dvisvgm(svg_text)
    if h <= 0:
        return MathRender(size=size, backend="latex")
    # LaTeX body is set at 12pt; scale so the result matches the requested size.
    scale = size / 12.0
    from .svgpath import scale_path_data, path_bbox
    d = scale_path_data(d, scale)
    x0, y0, x1, y1 = path_bbox(d)
    # dvisvgm puts the baseline of the first line at y = 0.
    return MathRender(d=d, width=max(0.0, x1 - x0), ascent=max(0.0, -y0),
                      descent=max(0.0, y1), x_offset=x0, size=size,
                      backend="latex")


def _flatten_dvisvgm(svg_text: str) -> tuple:
    """Resolve ``<use>`` references from dvisvgm output into one path."""
    ns = "{http://www.w3.org/2000/svg}"
    root = ET.fromstring(svg_text)
    defs: dict = {}
    for path in root.iter(f"{ns}path"):
        pid = path.get("id")
        if pid:
            defs[pid] = path.get("d", "")

    from .svgpath import translate_path_data, scale_path_data

    parts = []

    def walk(node, tx: float, ty: float, sc: float):
        tag = node.tag.replace(ns, "")
        t = node.get("transform")
        if t:
            for m in re.finditer(r"(translate|scale|matrix)\(([^)]*)\)", t):
                kind, args = m.group(1), [float(x) for x in
                                          re.split(r"[,\s]+", m.group(2).strip())
                                          if x]
                if kind == "translate":
                    tx += args[0] * sc
                    ty += (args[1] if len(args) > 1 else 0.0) * sc
                elif kind == "scale":
                    sc *= args[0]
                elif kind == "matrix" and len(args) == 6:
                    sc *= args[0]
                    tx += args[4]
                    ty += args[5]
        if tag == "use":
            href = (node.get("{http://www.w3.org/1999/xlink}href")
                    or node.get("href") or "")
            ref = defs.get(href.lstrip("#"))
            if ref:
                x = float(node.get("x", 0) or 0) * sc + tx
                y = float(node.get("y", 0) or 0) * sc + ty
                d = scale_path_data(ref, sc) if sc != 1.0 else ref
                parts.append(translate_path_data(d, x, y))
        elif tag == "path" and node.get("id") is None:
            d = scale_path_data(node.get("d", ""), sc) if sc != 1.0 else node.get("d", "")
            parts.append(translate_path_data(d, tx, ty))
        elif tag == "rect":
            x = float(node.get("x", 0) or 0) * sc + tx
            y = float(node.get("y", 0) or 0) * sc + ty
            w = float(node.get("width", 0) or 0) * sc
            h = float(node.get("height", 0) or 0) * sc
            parts.append(f"M{x} {y}h{w}v{h}h{-w}Z")
        for child in node:
            walk(child, tx, ty, sc)

    for child in root:
        if child.tag == f"{ns}defs":
            continue
        walk(child, 0.0, 0.0, 1.0)

    d = "".join(parts)
    from .svgpath import path_bbox
    x0, y0, x1, y1 = path_bbox(d) if d else (0, 0, 0, 0)
    return d, x1 - x0, y1 - y0


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=2048)
def render_math(expr: str, size: float = 12.0, backend: str = "auto",
                display: bool = False) -> MathRender:
    """Typeset ``expr`` and return outlines with the baseline at ``y = 0``."""
    expr = expr.strip()
    if not expr:
        return MathRender(size=size)
    backend = (backend or "auto").lower()
    if backend == "auto":
        backend = "mathtext"
    if backend == "latex":
        return _render_latex(expr, size, display=display)
    if backend == "mathtext":
        return _render_mathtext(expr, size)
    raise MathError(f"unknown math backend {backend!r}")
