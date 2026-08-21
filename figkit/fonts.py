"""Font resolution and text measurement.

Layout quality lives or dies on knowing how wide a string is.  We resolve a
CSS-ish ``font-family`` list to an actual font file (via fontconfig when
available, otherwise by scanning the usual directories), then measure with
real glyph advances from the font's ``hmtx`` table.

If no font file can be found at all we fall back to the PostScript core-font
width tables (Helvetica/Times/Courier), which are close enough for layout.
"""

from __future__ import annotations

import functools
import io
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

__all__ = [
    "Font", "FontMetrics", "get_font", "measure_text", "text_extents",
    "register_font", "font_dirs", "clear_cache",
]

# --------------------------------------------------------------------------
# Core-font fallback widths (units per 1000 em, characters 32..126)
# --------------------------------------------------------------------------

_CORE = {
    "helvetica": (
        "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
        "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
        "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
        "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
        "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
        "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584"),
    "helvetica-bold": (
        "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
        "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 "
        "975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 "
        "667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 "
        "333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 "
        "611 611 389 556 333 611 556 778 556 556 500 389 280 389 584"),
    "times": (
        "250 333 408 500 500 833 778 180 333 333 500 564 250 333 250 278 "
        "500 500 500 500 500 500 500 500 500 500 278 278 564 564 564 444 "
        "921 722 667 667 722 611 556 722 722 333 389 722 611 889 722 722 "
        "556 722 667 556 611 722 722 944 722 722 611 333 278 333 469 500 "
        "333 444 500 444 500 444 333 500 500 278 278 500 278 778 500 500 "
        "500 500 333 389 278 500 500 722 500 500 444 480 200 480 541"),
    "times-bold": (
        "250 333 555 500 500 1000 833 278 333 333 500 570 250 333 250 278 "
        "500 500 500 500 500 500 500 500 500 500 333 333 570 570 570 500 "
        "930 722 667 722 722 667 611 778 778 389 500 778 667 944 722 778 "
        "611 778 722 556 667 722 722 1000 722 722 667 333 278 333 581 500 "
        "333 500 556 444 556 444 333 500 556 278 333 556 278 833 556 500 "
        "556 556 444 389 333 556 500 722 500 500 444 394 220 394 520"),
}
_CORE_WIDTHS = {k: [int(x) for x in v.split()] for k, v in _CORE.items()}

# Generic family -> concrete candidates, in preference order.
_GENERIC = {
    "sans-serif": ["Inter", "Helvetica Neue", "Helvetica", "Arial",
                   "Liberation Sans", "DejaVu Sans", "FreeSans", "Segoe UI",
                   "Roboto", "Noto Sans"],
    "sans": ["Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"],
    "serif": ["Latin Modern Roman", "Georgia", "Times New Roman", "Times",
              "Liberation Serif", "DejaVu Serif", "FreeSerif", "Noto Serif"],
    "monospace": ["SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono",
                  "Liberation Mono", "Courier New", "FreeMono", "Noto Sans Mono"],
    "mono": ["DejaVu Sans Mono", "Liberation Mono", "Courier New"],
    "cursive": ["Comic Sans MS", "DejaVu Sans"],
    "system-ui": ["Inter", "Segoe UI", "Helvetica", "DejaVu Sans"],
    "ui-monospace": ["SF Mono", "Menlo", "DejaVu Sans Mono"],
    "ui-sans-serif": ["Inter", "Helvetica", "DejaVu Sans"],
}

_EXTS = (".ttf", ".otf", ".ttc", ".otc")

_registered: dict = {}       # lowercase family -> {(weight, style): path}
_dir_index: dict | None = None


def font_dirs() -> list:
    """Directories searched for font files."""
    dirs = []
    env = os.environ.get("FIGKIT_FONT_PATH")
    if env:
        dirs += [d for d in env.split(os.pathsep) if d]
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        dirs += ["/System/Library/Fonts", "/Library/Fonts",
                 os.path.join(home, "Library/Fonts"),
                 "/System/Library/Fonts/Supplemental"]
    elif os.name == "nt":
        dirs += [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""),
                              "Microsoft", "Windows", "Fonts")]
    else:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts",
                 os.path.join(home, ".fonts"),
                 os.path.join(home, ".local/share/fonts")]
    return [d for d in dirs if d and os.path.isdir(d)]


def register_font(family: str, path: str, weight="normal", style="normal") -> None:
    """Teach figkit about a font file so it can be measured and embedded."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    key = family.strip().lower()
    _registered.setdefault(key, {})[(_wnum(weight), _snorm(style))] = path
    clear_cache()


def clear_cache() -> None:
    global _dir_index
    _dir_index = None
    _resolve_family.cache_clear()
    _load_font.cache_clear()
    measure_text.cache_clear()


def _wnum(weight) -> int:
    if isinstance(weight, (int, float)):
        return int(weight)
    w = str(weight).lower()
    return {"thin": 100, "extralight": 200, "ultralight": 200, "light": 300,
            "normal": 400, "regular": 400, "book": 400, "medium": 500,
            "semibold": 600, "demibold": 600, "bold": 700, "extrabold": 800,
            "ultrabold": 800, "black": 900, "heavy": 900,
            "lighter": 300, "bolder": 700}.get(w, 400)


def _snorm(style) -> str:
    s = str(style or "normal").lower()
    return "italic" if s in ("italic", "oblique") else "normal"


def split_family(family) -> list:
    """Split a CSS font-family list into concrete candidate names."""
    if family is None:
        return []
    if isinstance(family, (list, tuple)):
        parts = list(family)
    else:
        parts = [p.strip() for p in str(family).split(",")]
    out = []
    for p in parts:
        p = str(p).strip().strip("'\"").strip()
        if not p:
            continue
        low = p.lower()
        if low in _GENERIC:
            out.extend(_GENERIC[low])
            out.append(low)
        else:
            out.append(p)
    return out


# --------------------------------------------------------------------------
# Locating font files
# --------------------------------------------------------------------------

def _build_dir_index() -> dict:
    """Map ``lowercase filename stem -> path`` for every font we can see."""
    global _dir_index
    if _dir_index is not None:
        return _dir_index
    index: dict = {}
    for root_dir in font_dirs():
        for root, _dirs, files in os.walk(root_dir):
            for fn in files:
                if fn.lower().endswith(_EXTS):
                    stem = os.path.splitext(fn)[0].lower()
                    index.setdefault(stem, os.path.join(root, fn))
                    index.setdefault(re.sub(r"[^a-z0-9]", "", stem),
                                     os.path.join(root, fn))
    _dir_index = index
    return index


def _fc_match(name: str, weight: int, style: str) -> str | None:
    fc = shutil.which("fc-match")
    if not fc:
        return None
    pattern = name
    if weight >= 600:
        pattern += ":bold"
    if style == "italic":
        pattern += ":italic"
    try:
        out = subprocess.run([fc, "-f", "%{file}", pattern],
                             capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    path = out.stdout.strip()
    if path and os.path.isfile(path) and path.lower().endswith(_EXTS):
        # fc-match always answers; make sure the answer is actually related.
        stem = re.sub(r"[^a-z0-9]", "", os.path.splitext(os.path.basename(path))[0].lower())
        want = re.sub(r"[^a-z0-9]", "", name.lower())
        if want[:6] in stem or stem[:6] in want or want in stem:
            return path
        return path if name.lower() in _GENERIC else None
    return None


def _guess_filenames(name: str, weight: int, style: str) -> list:
    base = re.sub(r"[^A-Za-z0-9]", "", name)
    bold = weight >= 600
    suffixes = []
    if bold and style == "italic":
        suffixes = ["BoldItalic", "-BoldItalic", "bi", "-BoldOblique", "Z"]
    elif bold:
        suffixes = ["Bold", "-Bold", "bd", "b", "-Heavy"]
    elif style == "italic":
        suffixes = ["Italic", "-Italic", "i", "-Oblique"]
    else:
        suffixes = ["Regular", "-Regular", "", "-Book", "Book"]
    cands = [base + s for s in suffixes]
    cands += [base + "-" + s.lstrip("-") for s in suffixes if s]
    if not bold and style == "normal":
        cands.append(base)
    return [re.sub(r"[^a-z0-9]", "", c.lower()) for c in cands]


@functools.lru_cache(maxsize=512)
def _resolve_family(family: str, weight: int, style: str) -> str | None:
    for name in split_family(family):
        reg = _registered.get(name.lower())
        if reg:
            for key in ((weight, style), (weight, "normal"),
                        (400, style), (400, "normal")):
                if key in reg:
                    return reg[key]
            return next(iter(reg.values()))
    index = _build_dir_index()
    for name in split_family(family):
        for cand in _guess_filenames(name, weight, style):
            if cand in index:
                return index[cand]
    for name in split_family(family):
        hit = _fc_match(name, weight, style)
        if hit:
            return hit
    return None


@dataclass(frozen=True)
class FontMetrics:
    """Vertical metrics, expressed as a fraction of the em size."""

    ascent: float = 0.8
    descent: float = 0.2          # positive, measured downward
    line_gap: float = 0.0
    cap_height: float = 0.7
    x_height: float = 0.52
    units_per_em: int = 1000

    @property
    def line_height(self) -> float:
        return self.ascent + self.descent + self.line_gap


class Font:
    """A measurable font. Use :func:`get_font` rather than constructing one."""

    def __init__(self, family: str, weight=400, style="normal", path: str = None):
        self.family = family
        self.weight = _wnum(weight)
        self.style = _snorm(style)
        self.path = path
        self._tt = None
        self._cmap = None
        self._hmtx = None
        self._glyphset = None
        self._kern = None
        self._bytes: bytes | None = None
        self.metrics = FontMetrics()
        self._core = self._pick_core()
        if path:
            self._load()

    # -- loading --------------------------------------------------------
    def _pick_core(self) -> list:
        names = " ".join(split_family(self.family)).lower()
        bold = self.weight >= 600
        if "courier" in names or "mono" in names:
            return [600] * 95
        if "times" in names or "serif" in names or "georgia" in names:
            return _CORE_WIDTHS["times-bold" if bold else "times"]
        return _CORE_WIDTHS["helvetica-bold" if bold else "helvetica"]

    def _load(self) -> None:
        try:
            from fontTools.ttLib import TTFont, TTCollection
        except ImportError:
            self.path = None
            return
        try:
            # Read into memory rather than handing TTFont a path: lazy=True
            # would otherwise hold an OS file handle open for the process's
            # lifetime, and a figure using many faces can exhaust the limit.
            with open(self.path, "rb") as fh:
                self._bytes = fh.read()
            if self.path.lower().endswith((".ttc", ".otc")):
                coll = TTCollection(io.BytesIO(self._bytes), lazy=True,
                                    fontNumber=0)
                tt = coll.fonts[0]
            else:
                tt = TTFont(io.BytesIO(self._bytes), lazy=True, fontNumber=0)
            self._tt = tt
            upem = tt["head"].unitsPerEm
            hhea = tt["hhea"]
            asc, desc, gap = hhea.ascent, -hhea.descent, hhea.lineGap
            os2 = tt.get("OS/2")
            if os2 is not None and getattr(os2, "sTypoAscender", 0):
                if getattr(os2, "fsSelection", 0) & 128:  # USE_TYPO_METRICS
                    asc = os2.sTypoAscender
                    desc = -os2.sTypoDescender
                    gap = os2.sTypoLineGap
            cap = getattr(os2, "sCapHeight", 0) or 0
            xh = getattr(os2, "sxHeight", 0) or 0
            self.metrics = FontMetrics(
                ascent=asc / upem, descent=desc / upem, line_gap=gap / upem,
                cap_height=(cap / upem) if cap else 0.72 * (asc / upem) / 0.8,
                x_height=(xh / upem) if xh else 0.52,
                units_per_em=upem,
            )
            self._cmap = tt.getBestCmap()
            self._hmtx = tt["hmtx"]
        except Exception:
            self._tt = None
            self.path = None

    @property
    def available(self) -> bool:
        return self._tt is not None

    @property
    def upem(self) -> int:
        return self.metrics.units_per_em

    # -- measurement ----------------------------------------------------
    def glyph_name(self, ch: str):
        if self._cmap is None:
            return None
        return self._cmap.get(ord(ch))

    def char_advance(self, ch: str) -> float:
        """Advance width of one character, as a fraction of the em."""
        if self._tt is not None:
            gname = self.glyph_name(ch)
            if gname is None:
                for alt in (".notdef",):
                    gname = alt
            try:
                return self._hmtx[gname][0] / self.upem
            except Exception:
                return 0.5
        code = ord(ch)
        if 32 <= code <= 126:
            return self._core[code - 32] / 1000.0
        if ch == "\t":
            return 4 * self._core[0] / 1000.0
        if code < 32:
            return 0.0
        if 0x4E00 <= code <= 0x9FFF or 0x3000 <= code <= 0x30FF:
            return 1.0
        return 0.55

    def string_width(self, text: str, size: float = 1.0,
                     letter_spacing: float = 0.0) -> float:
        if not text:
            return 0.0
        total = sum(self.char_advance(c) for c in text) * size
        if letter_spacing:
            total += letter_spacing * (len(text) - 1)
        return total

    # -- outlines -------------------------------------------------------
    def glyph_set(self):
        if self._glyphset is None and self._tt is not None:
            self._glyphset = self._tt.getGlyphSet()
        return self._glyphset

    def text_to_path(self, text: str, size: float = 1.0,
                     letter_spacing: float = 0.0) -> str:
        """SVG path data for ``text`` on a baseline at the origin (y down)."""
        gs = self.glyph_set()
        if gs is None:
            return ""
        try:
            from fontTools.pens.svgPathPen import SVGPathPen
            from fontTools.pens.transformPen import TransformPen
        except ImportError:
            return ""
        scale = size / self.upem
        pen_out = SVGPathPen(gs, ntos=lambda v: f"{v:.3f}".rstrip("0").rstrip("."))
        x = 0.0
        for ch in text:
            gname = self.glyph_name(ch)
            if gname is None or gname not in gs:
                x += self.char_advance(ch) * size + letter_spacing
                continue
            # flip y (font space is y-up, SVG is y-down) and place at x
            tpen = TransformPen(pen_out, (scale, 0, 0, -scale, x, 0))
            try:
                gs[gname].draw(tpen)
            except Exception:
                pass
            x += self.char_advance(ch) * size + letter_spacing
        return pen_out.getCommands()

    def font_data(self) -> bytes | None:
        """Raw bytes of the font file (for embedding in exported SVG)."""
        if self._bytes is not None:
            return self._bytes
        if not self.path:
            return None
        try:
            with open(self.path, "rb") as fh:
                self._bytes = fh.read()
            return self._bytes
        except OSError:
            return None

    def __repr__(self) -> str:
        where = os.path.basename(self.path) if self.path else "core-metrics"
        return f"<Font {self.family!r} {self.weight} {self.style} [{where}]>"


@functools.lru_cache(maxsize=64)
def _load_font(family: str, weight: int, style: str) -> Font:
    path = _resolve_family(family, weight, style)
    return Font(family, weight, style, path)


def get_font(family=None, weight="normal", style="normal") -> Font:
    """Resolve a font family list to a measurable :class:`Font`."""
    fam = family if isinstance(family, str) else ", ".join(family or ["sans-serif"])
    return _load_font(fam or "sans-serif", _wnum(weight), _snorm(style))


@functools.lru_cache(maxsize=8192)
def measure_text(text: str, family=None, size: float = 14.0, weight="normal",
                 style="normal", letter_spacing: float = 0.0) -> float:
    """Width in px of a single line of text."""
    if not text:
        return 0.0
    return get_font(family, weight, style).string_width(text, size, letter_spacing)


def text_extents(text: str, family=None, size: float = 14.0, weight="normal",
                 style="normal", letter_spacing: float = 0.0) -> tuple:
    """``(width, ascent, descent)`` in px for one line."""
    f = get_font(family, weight, style)
    return (f.string_width(text, size, letter_spacing),
            f.metrics.ascent * size, f.metrics.descent * size)
