import pytest

from figkit import (Box, Circle, Diamond, Ellipse, Group, Image, Line, Matrix,
                    Path, Pill, Polygon, Polyline, Style, Text, Vector,
                    measure_text)
from figkit.fonts import get_font
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
