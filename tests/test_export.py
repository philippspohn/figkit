"""Export fallbacks and the warnings that keep failures from being silent."""

import sys
import types
import warnings

import pytest

from figkit import Box, Figure, Text, available_backends
from figkit.export import ExportError, _cairosvg


def test_a_broken_cairosvg_does_not_abort_the_fallback_chain(monkeypatch):
    """cairosvg raises OSError when its native library is missing.

    Catching only ImportError there would end the export instead of trying
    rsvg-convert / resvg / inkscape / chromium next.
    """
    class Exploding(types.ModuleType):
        def __getattr__(self, name):
            raise OSError("no library called 'cairo-2' was found")

    monkeypatch.setitem(sys.modules, "cairosvg", Exploding("cairosvg"))
    assert _cairosvg("<svg/>", "png") is None          # falls through, no raise


def test_a_failing_cairosvg_call_warns_and_falls_through(monkeypatch):
    fake = types.ModuleType("cairosvg")

    def boom(**kwargs):
        raise RuntimeError("conversion failed")

    fake.svg2png = boom
    fake.svg2pdf = boom
    fake.svg2ps = boom
    monkeypatch.setitem(sys.modules, "cairosvg", fake)
    with pytest.warns(UserWarning, match="cairosvg backend failed"):
        assert _cairosvg("<svg/>", "png") is None


def test_missing_backends_raise_export_error(monkeypatch):
    monkeypatch.setattr("figkit.export._cairosvg", lambda *a, **k: None)
    monkeypatch.setattr("figkit.export.shutil.which", lambda name: None)
    monkeypatch.setattr("figkit.export._chromium", lambda: None)
    with Figure() as fig:
        Box("hi")
    with pytest.raises(ExportError, match="no PNG backend"):
        fig.to_png()


def test_export_warns_when_text_could_not_be_outlined(monkeypatch):
    """Raster export outlines text; falling back to <text> reintroduces a
    dependency on the converter's fonts, so it must not be silent."""
    import figkit.text as text_module

    real = text_module.get_font

    class NoOutlines:
        available = False
        metrics = real(None).metrics

        def string_width(self, *a, **k):
            return real(None).string_width(*a, **k)

        def text_to_path(self, *a, **k):
            return ""

    monkeypatch.setattr(text_module, "get_font", lambda *a, **k: NoOutlines())
    monkeypatch.setattr("figkit.export._rasterize",
                        lambda *a, **k: b"\x89PNG\r\n\x1a\n")
    with Figure() as fig:
        Text("hello")
    with pytest.warns(UserWarning, match="no outline font"):
        fig.to_png()


def test_text_is_outlined_when_a_font_is_available():
    from figkit.fonts import get_font
    if not get_font("sans-serif").available:
        pytest.skip("no outline font on this machine")
    with Figure() as fig:
        Text("outline me")
    assert "<text" not in fig.to_svg(text_as_paths=True)


def test_available_backends_reports_booleans():
    backends = available_backends()
    assert set(backends) >= {"cairosvg", "rsvg-convert", "resvg"}
    assert all(isinstance(v, bool) for v in backends.values())


def test_svg_and_html_need_no_backend(tmp_path):
    with Figure() as fig:
        Box("hi $x^2$")
    assert fig.save(tmp_path / "f.svg").endswith(".svg")
    assert fig.save(tmp_path / "f.html").endswith(".html")
