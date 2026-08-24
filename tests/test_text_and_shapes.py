import pytest

from figkit import (Box, Circle, Diamond, Dot, Ellipse, Group, Image, Line,
                    Matrix, Path, Pill, Polygon, Polyline, Style, Text, Vector,
                    measure_text)
from figkit.fonts import get_font
from figkit.mathtext import math_available
from figkit.svgdoc import RenderContext
from figkit.text import layout_text


def render(el):
    node = el.render(RenderContext())
    return node.render() if node is not None else ""


# -- measurement -----------------------------------------------------------

def test_measure_text_scales_with_size_and_length():
    w1 = measure_text("hello", "sans-serif", 14)
    w2 = measure_text("hello", "sans-serif", 28)
    assert w2 == pytest.approx(w1 * 2, rel=1e-6)
    assert measure_text("hellohello", "sans-serif", 14) > w1
    assert measure_text("", "sans-serif", 14) == 0


def test_font_falls_back_when_missing():
    f = get_font("Definitely Not Installed 12345")
    assert f.string_width("iiii", 14) < f.string_width("MMMM", 14)


def test_layout_multiline():
    lay = layout_text("one\ntwo\nthree", font_size=10, line_height=1.5)
    assert len(lay.lines) == 3
    assert lay.height == pytest.approx(3 * 15, abs=0.5)
    assert lay.lines[1].baseline > lay.lines[0].baseline


def test_layout_wrapping():
    lay = layout_text("aaa bbb ccc ddd eee fff", font_size=12, max_width=60)
    assert len(lay.lines) > 1
    assert all(ln.width <= 62 for ln in lay.lines)


@pytest.mark.skipif(not math_available(), reason="needs matplotlib")
def test_inline_math_produces_paths():
    t = Text("value $x^2$ here", add=False)
    out = render(t)
    assert "<path" in out and "<text" in out
    assert t.bbox.w > measure_text("value  here", None, 14)


def test_text_alignment_anchors():
    left = Text("hello", align="left", add=False)
    right = Text("hello", align="right", add=False)
    assert left.bbox.w == pytest.approx(right.bbox.w)


def test_text_as_paths_emits_no_text_nodes():
    t = Text("outline me", add=False)
    node = t.render(RenderContext(text_as_paths=True))
    assert "<text" not in node.render()
    assert "<path" in node.render()


def test_markup_bold_italic():
    t = Text("plain **bold** and *it*", markup=True, add=False)
    out = render(t)
    assert 'font-weight="bold"' in out
    assert 'font-style="italic"' in out


# -- boxes -----------------------------------------------------------------

def test_box_autosizes_around_label():
    small = Box("hi", add=False)
    big = Box("a much longer label", add=False)
    assert big.bbox.w > small.bbox.w
    assert small.bbox.h == pytest.approx(big.bbox.h)


def test_box_padding_controls_size():
    tight = Box("hi", padding=0, add=False)
    loose = Box("hi", padding=20, add=False)
    assert loose.bbox.w == pytest.approx(tight.bbox.w + 40)
    assert loose.bbox.h == pytest.approx(tight.bbox.h + 40)


def test_box_explicit_width_wraps_label():
    b = Box("one two three four five six", w=80, add=False)
    assert b.bbox.w == 80
    assert len(b.label.layout.lines) > 1


def test_box_label_is_centred():
    b = Box("hi", w=200, h=100, add=False)
    band = b.label.optical_bbox
    assert band.center.x == pytest.approx(b.bbox.center.x, abs=0.5)
    assert band.center.y == pytest.approx(b.bbox.center.y, abs=0.5)


def test_box_valign_top():
    b = Box("hi", w=200, h=100, valign="top", padding=10, add=False)
    assert b.label.bbox.y0 == pytest.approx(b.bbox.y0 + 10, abs=0.5)


def test_box_radius_and_pill():
    assert 'rx="6"' in render(Box("x", radius=6, add=False))
    p = Pill("x", add=False)
    assert f'rx="{p.bbox.h / 2:g}"' in render(p) or "rx=" in render(p)


def test_min_size_respected():
    b = Box("x", min_w=250, min_h=90, add=False)
    assert b.bbox.w == 250 and b.bbox.h == 90


def test_shapes_render_paths():
    assert "<ellipse" in render(Ellipse("x", add=False))
    assert "<path" in render(Diamond("x", add=False))
    c = Circle("x", r=30, add=False)
    assert c.bbox.w == c.bbox.h == 60


# -- geometry primitives ---------------------------------------------------

def test_path_bbox_is_exact():
    p = Path("M0 0 C 0 100 100 100 100 0", add=False)
    assert p.bbox.x0 == 0 and p.bbox.x1 == 100
    assert p.bbox.y1 == pytest.approx(75, abs=0.01)


def test_path_resize_scales():
    p = Path("M0 0 L10 0 L10 10 Z", add=False)
    p.resize(w=100)
    assert p.bbox.w == pytest.approx(100)
    assert p.bbox.h == pytest.approx(100)


def test_polyline_moves_with_group():
    poly = Polyline([(0, 0), (10, 10)], add=False)
    g = Group(poly, add=False)
    g.move(50, 5)
    assert poly.points[0].x == 50
    assert poly.bbox.x0 == 50


def test_line_tracks_live_anchors():
    a = Box("a", add=False)
    b = Box("b", add=False).right_of(a, gap=40)
    ln = Line(a.e, b.w, add=False)
    assert ln.bbox.w == pytest.approx(40)
    b.move(0, 30)
    assert ln.bbox.h == pytest.approx(30)


def test_polygon_is_closed():
    assert render(Polygon([(0, 0), (10, 0), (5, 9)], add=False)).count("Z") >= 1


# -- matrices --------------------------------------------------------------

def test_matrix_geometry_and_cells():
    m = Matrix([[0, 1], [1, 0]], cell=20, gap=2, add=False)
    assert m.shape() == (2, 2)
    assert m.bbox.w == pytest.approx(42)
    assert m.cell(1, 1).bbox.anchor("nw").x == pytest.approx(22)


def test_matrix_colours_from_cmap():
    m = Matrix([[0.0, 1.0]], cmap="viridis", add=False)
    assert m.cell(0, 0).prop("fill") != m.cell(0, 1).prop("fill")


def test_matrix_forwards_paint_kwargs_to_cells():
    m = Matrix([[0, 1]], stroke="#123456", add=False)
    assert m.cell(0, 0).prop("stroke") == "#123456"


def test_vector_orientation():
    assert Vector([1, 2, 3], cell=10, add=False).shape() == (3, 1)
    assert Vector([1, 2, 3], orient="h", cell=10, add=False).shape() == (1, 3)


# -- images ----------------------------------------------------------------

SVG_SRC = ('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20" '
           'viewBox="0 0 40 20"><defs><linearGradient id="g"/></defs>'
           '<rect width="40" height="20" fill="url(#g)"/></svg>')


def test_image_natural_size_and_aspect():
    im = Image(SVG_SRC, w=80, add=False)
    assert im.natural_size == (40.0, 20.0)
    assert im.bbox.h == pytest.approx(40)


def test_inline_svg_namespaces_ids():
    out = render(Image(SVG_SRC, w=80, add=False))
    assert 'id="svg1_g"' in out
    assert "url(#svg1_g)" in out


def test_png_bytes_are_embedded():
    # 8-byte signature, 4-byte chunk length, "IHDR", then width/height
    png = (b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR"
           + (16).to_bytes(4, "big") + (8).to_bytes(4, "big") + b"\x00" * 40)
    im = Image(png, mime="image/png", add=False)
    assert im.natural_size == (16.0, 8.0)
    assert "data:image/png;base64," in render(im)


# -- rich text spans -------------------------------------------------------

def test_span_overrides_only_what_it_sets():
    from figkit import Span
    span = Span("x", color="red", bold=True)
    assert span.overrides() == {"color": "red", "weight": "bold"}
    assert Span("x").overrides() == {}
    assert Span("x", bold=False).overrides() == {"weight": "normal"}
    assert Span("x", strike=True).overrides()["decoration"] == ("strike",)


def test_spans_produce_separately_styled_runs():
    from figkit import Span
    from figkit.text import layout_text
    lay = layout_text(["plain ", Span("red", color="#ff0000", bold=True),
                       " tail"], font_size=14)
    runs = lay.lines[0].runs
    assert [r.content for r in runs] == ["plain ", "red", " tail"]
    assert runs[1].color == "#ff0000" and runs[1].weight == "bold"
    assert runs[0].color is None and runs[2].weight == "normal"


def test_span_colour_reaches_the_svg():
    from figkit import Span
    out = render(Text(["a ", Span("b", color="#123456")], add=False))
    assert '#123456' in out


def test_span_size_changes_measured_width():
    from figkit import Span
    small = Text(["word"], font_size=10, add=False).bbox.w
    big = Text([Span("word", size=30)], font_size=10, add=False).bbox.w
    assert big > small * 2.5


def test_decorations_are_drawn_as_geometry_not_attributes():
    """text-decoration is dropped by rasterisers and by outlining, so the
    rules must be real geometry."""
    from figkit import Span
    plain = render(Text([Span("struck", strike=True)], add=False))
    assert "<rect" in plain
    outlined = Text([Span("struck", strike=True)], add=False).render(
        RenderContext(text_as_paths=True)).render()
    assert "<rect" in outlined and "<text" not in outlined


def test_underline_and_strike_sit_on_opposite_sides_of_the_baseline():
    from figkit import Span
    import re
    strike = Text([Span("x", strike=True)], add=False)
    under = Text([Span("x", underline=True)], add=False)
    ys = [float(re.search(r'<rect[^>]*y="([\d.-]+)"', render(t)).group(1))
          for t in (strike, under)]
    assert ys[0] < ys[1]


def test_spans_survive_wrapping():
    from figkit import Span
    from figkit.text import layout_text
    lay = layout_text(["one two ", Span("three four", color="blue"), " five"],
                      max_width=70, font_size=13)
    coloured = [r for line in lay.lines for r in line.runs if r.color == "blue"]
    assert len(coloured) >= 2                 # split across lines, still blue
    assert all(line.width <= 72 for line in lay.lines)


def test_spans_work_inside_a_box_label():
    from figkit import Span
    box = Box(["status: ", Span("FAILED", color="#ffffff", bold=True)],
              w=200, add=False)
    assert box.text == "status: FAILED"       # plain text for measurement/audit
    assert "#ffffff" in render(box)


def test_runs_only_merge_when_styling_matches():
    from figkit import Span
    from figkit.text import _merge_runs, layout_text
    lay = layout_text(["a ", Span("b", color="red"), " c"], font_size=12)
    assert len(_merge_runs(lay.lines[0].runs)) == 3
    lay2 = layout_text("a b c", font_size=12)
    assert len(_merge_runs(lay2.lines[0].runs)) == 1


def test_math_degrades_to_plain_text_without_matplotlib(monkeypatch):
    """A missing optional dependency should not blow up a whole figure."""
    import figkit.text as text_module
    from figkit.mathtext import MathError

    def unavailable(*a, **k):
        raise MathError("math rendering needs matplotlib")

    monkeypatch.setattr(text_module, "render_math", unavailable)
    monkeypatch.setattr(text_module, "math_available", lambda: False)
    box = Box("value $x^2$ here", add=False)
    with pytest.warns(UserWarning, match="needs matplotlib"):
        out = render(box)                    # measurement is lazy
    assert "x^2" in out                      # set as source, still readable
    assert box.bbox.w > 0


def test_a_genuine_tex_error_still_raises(monkeypatch):
    import figkit.text as text_module
    from figkit.mathtext import MathError

    def broken(*a, **k):
        raise MathError("could not typeset")

    monkeypatch.setattr(text_module, "render_math", broken)
    monkeypatch.setattr(text_module, "math_available", lambda: True)
    with pytest.raises(MathError):
        Box("$\\frac{$", add=False).bbox


# -- rotation, glyphs, dots -------------------------------------------------

@pytest.mark.parametrize("text", ["ab", "abcdefghij", "abcdefghij" * 2])
def test_a_rotated_label_stays_where_you_put_it(text):
    """Pivoting on the block's centre displaced it by half its own length, so
    where a rotated label landed depended on how many characters it had."""
    t = Text(text, x=100, y=100, rotate=-90, add=False)
    assert t.bbox.x == pytest.approx(100)


def test_rotate_about_still_takes_an_explicit_pivot():
    plain = Text("abcdefghij", x=100, y=100, add=False)
    turned = Text("abcdefghij", x=100, y=100, rotate=-90,
                  rotate_about=plain.bbox.center, add=False)
    assert turned.bbox.center.x == pytest.approx(plain.bbox.center.x)
    assert turned.bbox.center.y == pytest.approx(plain.bbox.center.y)


def test_a_missing_glyph_says_so_instead_of_measuring_notdef():
    """measure_text used to hand back .notdef's width — a confident number for
    a character the font does not have."""
    import warnings

    from figkit.fonts import clear_cache, get_font, measure_text

    font = get_font()
    if font._cmap is None:
        pytest.skip("no real font file on this machine")
    missing = next((chr(c) for c in range(0x2100, 0x2200)
                    if c not in font._cmap), None)
    if missing is None:
        pytest.skip("this font covers the whole probe range")

    clear_cache()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        measure_text(missing, size=14)
    assert any("no glyph" in str(c.message) for c in caught)
    assert any(f"U+{ord(missing):04X}" in str(c.message) for c in caught)


def test_the_missing_glyph_warning_does_not_repeat():
    import warnings

    from figkit.fonts import clear_cache, get_font, measure_text

    font = get_font()
    if font._cmap is None:
        pytest.skip("no real font file on this machine")
    missing = next((chr(c) for c in range(0x2100, 0x2200)
                    if c not in font._cmap), None)
    if missing is None:
        pytest.skip("this font covers the whole probe range")

    clear_cache()
    measure_text(missing, size=14)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        measure_text(missing, size=11)          # a different size, same glyph
    assert not [c for c in caught if "no glyph" in str(c.message)]


@pytest.mark.parametrize("dot", [
    Dot((10, 20), 5, add=False),
    Dot((10, 20), r=5, add=False),
    Dot(10, 20, 5, add=False),
    Dot(10, 20, r=5, add=False),
])
def test_dot_takes_a_centre_or_a_pair_of_coordinates(dot):
    assert dot.r == 5
    assert dot.bbox.center.x == pytest.approx(10)
    assert dot.bbox.center.y == pytest.approx(20)
