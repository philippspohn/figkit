"""Exporting figures to SVG, PNG, PDF and HTML.

SVG is written natively.  PNG/PDF go through cairosvg when it is installed,
and otherwise fall back to whichever converter is on ``PATH``
(``rsvg-convert``, ``resvg``, ``inkscape``, ``chromium``).
"""

from __future__ import annotations

import os
import warnings
import shutil
import subprocess
import tempfile

__all__ = ["save_figure", "to_png", "to_pdf", "to_svg", "to_html",
           "available_backends", "ExportError"]


class ExportError(RuntimeError):
    """Raised when a figure cannot be converted to the requested format."""


_RASTER_FORMATS = {"png", "jpg", "jpeg", "webp"}
_VECTOR_FORMATS = {"svg", "pdf", "ps", "eps"}


def available_backends() -> dict:
    """Which conversion backends this machine can use."""
    out = {"cairosvg": False, "rsvg-convert": False, "resvg": False,
           "inkscape": False, "chromium": False}
    try:
        import cairosvg  # noqa: F401  (import is the availability check)
        out["cairosvg"] = True
    except Exception:
        pass
    for name in ("rsvg-convert", "resvg", "inkscape"):
        out[name] = bool(shutil.which(name))
    out["chromium"] = bool(shutil.which("chromium") or shutil.which("chrome")
                           or shutil.which("google-chrome")
                           or shutil.which("chromium-browser"))
    return out


def _ext(path) -> str:
    return os.path.splitext(str(path))[1].lstrip(".").lower()


def save_figure(fig, path, *, scale: float = None, dpi: float = None,
                format: str = None, **kw) -> str:
    """Save ``fig`` to ``path``; the format comes from the extension."""
    path = os.fspath(path)
    fmt = (format or _ext(path) or "svg").lower()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    if fmt == "svg":
        svg = fig.to_svg(**kw)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        return os.path.abspath(path)
    if fmt in ("html", "htm"):
        html_kw = {k: v for k, v in kw.items()
                   if k in ("title", "background", "text_as_paths",
                            "embed_fonts", "pretty")}
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(fig.to_html(**html_kw))
        return os.path.abspath(path)
    if fmt in _RASTER_FORMATS:
        data = to_png(fig, None, scale=scale if scale is not None else 2.0,
                      dpi=dpi, fmt=fmt, **kw)
        with open(path, "wb") as fh:
            fh.write(data)
        return os.path.abspath(path)
    if fmt in _VECTOR_FORMATS:
        data = to_pdf(fig, None, fmt=fmt, **kw)
        with open(path, "wb") as fh:
            fh.write(data)
        return os.path.abspath(path)
    raise ExportError(
        f"unknown output format {fmt!r}; use svg, png, pdf or html")


def to_svg(fig, path=None, **kw):
    svg = fig.to_svg(**kw)
    if path is None:
        return svg
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    return os.path.abspath(path)


def to_html(fig, path=None, **kw):
    html = fig.to_html(**kw)
    if path is None:
        return html
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return os.path.abspath(path)


def _split_kw(kw: dict) -> tuple:
    """Separate SVG-rendering options from converter options."""
    svg_keys = ("pretty", "text_as_paths", "embed_fonts", "standalone")
    svg_kw = {k: v for k, v in kw.items() if k in svg_keys}
    rest = {k: v for k, v in kw.items() if k not in svg_keys}
    return svg_kw, rest


def to_png(fig, path=None, *, scale: float = 2.0, dpi: float = None,
           background=None, fmt: str = "png", **kw):
    """Rasterise a figure. Returns bytes when ``path`` is ``None``."""
    svg_kw, _ = _split_kw(kw)
    # Outlining text removes any dependency on the converter's font stack.
    svg_kw.setdefault("text_as_paths", True)
    svg = fig.to_svg(**svg_kw)
    vb = fig.viewbox()
    scale = float(scale if scale is not None else 2.0)
    if dpi:
        scale = float(dpi) / 96.0
    width = max(1, int(round(vb.w * fig.scale * scale)))
    height = max(1, int(round(vb.h * fig.scale * scale)))
    data = _rasterize(svg, width, height, background, fmt)
    if path is None:
        return data
    with open(path, "wb") as fh:
        fh.write(data)
    return os.path.abspath(path)


def to_pdf(fig, path=None, *, background=None, fmt: str = "pdf", **kw):
    """Export to PDF (or PS/EPS). Returns bytes when ``path`` is ``None``."""
    svg_kw, _ = _split_kw(kw)
    svg_kw.setdefault("text_as_paths", True)
    svg = fig.to_svg(**svg_kw)
    data = _vectorize(svg, fmt, background)
    if path is None:
        return data
    with open(path, "wb") as fh:
        fh.write(data)
    return os.path.abspath(path)


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------

def _cairosvg(svg: str, fmt: str, width=None, height=None, background=None):
    try:
        import cairosvg
    except ImportError:
        return None
    if "<filter" in svg:
        # cairosvg ignores filter primitives outright, so a shadow that shows
        # up in the SVG would silently vanish here. Say so rather than ship
        # two files that disagree.
        warnings.warn(
            "figkit: this figure uses an SVG filter (e.g. shadow=...), which "
            "the cairosvg backend ignores — the rasterised output will differ "
            "from the SVG. Drop the filter, or render with rsvg-convert / "
            "resvg / chromium.", stacklevel=3)
    fn = {"png": cairosvg.svg2png, "pdf": cairosvg.svg2pdf,
          "ps": cairosvg.svg2ps, "eps": cairosvg.svg2ps}.get(fmt)
    if fn is None:
        return None
    kwargs = {"bytestring": svg.encode("utf-8")}
    if width:
        kwargs["output_width"] = width
    if height:
        kwargs["output_height"] = height
    if background:
        kwargs["background_color"] = background
    return fn(**kwargs)


def _run_cli(cmd: list, svg: str, out_suffix: str) -> bytes | None:
    with tempfile.TemporaryDirectory(prefix="figkit-export-") as tmp:
        src = os.path.join(tmp, "figure.svg")
        dst = os.path.join(tmp, "figure" + out_suffix)
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(svg)
        real = [c.format(src=src, dst=dst) for c in cmd]
        try:
            proc = subprocess.run(real, capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0 or not os.path.exists(dst):
            return None
        with open(dst, "rb") as fh:
            return fh.read()


def _rasterize(svg: str, width: int, height: int, background, fmt: str) -> bytes:
    data = _cairosvg(svg, "png", width, height, background)
    if data:
        return data
    exe = shutil.which("rsvg-convert")
    if exe:
        cmd = [exe, "-w", str(width), "-h", str(height), "-o", "{dst}", "{src}"]
        if background:
            cmd[1:1] = ["-b", str(background)]
        data = _run_cli(cmd, svg, ".png")
        if data:
            return data
    exe = shutil.which("resvg")
    if exe:
        data = _run_cli([exe, "--width", str(width), "--height", str(height),
                         "{src}", "{dst}"], svg, ".png")
        if data:
            return data
    exe = shutil.which("inkscape")
    if exe:
        data = _run_cli([exe, "{src}", "--export-type=png",
                         f"--export-width={width}", f"--export-height={height}",
                         "--export-filename={dst}"], svg, ".png")
        if data:
            return data
    exe = _chromium()
    if exe:
        data = _run_cli([exe, "--headless", "--disable-gpu", "--no-sandbox",
                         f"--window-size={width},{height}",
                         "--default-background-color=00000000",
                         "--screenshot={dst}", "{src}"], svg, ".png")
        if data:
            return data
    raise ExportError(
        "no PNG backend available. Install one of:\n"
        "  pip install 'figkit[export]'      (cairosvg — recommended)\n"
        "  apt install librsvg2-bin          (rsvg-convert)\n"
        "  cargo install resvg               (resvg)\n"
        "Or export SVG and convert it yourself.")


def _vectorize(svg: str, fmt: str, background) -> bytes:
    data = _cairosvg(svg, fmt, background=background)
    if data:
        return data
    suffix = "." + fmt
    exe = shutil.which("rsvg-convert")
    if exe:
        data = _run_cli([exe, "-f", fmt, "-o", "{dst}", "{src}"], svg, suffix)
        if data:
            return data
    exe = shutil.which("inkscape")
    if exe:
        data = _run_cli([exe, "{src}", f"--export-type={fmt}",
                         "--export-filename={dst}"], svg, suffix)
        if data:
            return data
    exe = _chromium()
    if exe and fmt == "pdf":
        data = _run_cli([exe, "--headless", "--disable-gpu", "--no-sandbox",
                         "--print-to-pdf={dst}", "--no-pdf-header-footer",
                         "{src}"], svg, ".pdf")
        if data:
            return data
    raise ExportError(
        f"no {fmt.upper()} backend available. Install one of:\n"
        "  pip install 'figkit[export]'      (cairosvg — recommended)\n"
        "  apt install librsvg2-bin          (rsvg-convert)\n"
        "  apt install inkscape")


def _chromium() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        exe = shutil.which(name)
        if exe:
            return exe
    return None
