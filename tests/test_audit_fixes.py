"""Regressions found in the usability audit of b4ff029."""

import os
import re

import pytest

from figkit import (Box, ColorBar, Diamond, Ellipse, Figure, Frame, Group,
                    Marker, Matrix, Pill, Span, Text, Theme, Vector, connect,
                    grid, hstack, self_loop, vstack)
from figkit.export import ExportError
from figkit.fonts import Font, font_dirs
from figkit.style import UnknownProperty
from figkit.svgdoc import RenderContext
from figkit.svgpath import path_bbox


def test_ttc_fonts_load_when_one_is_available(tmp_path):
    """fontTools.TTCollection rejects TTFont's fontNumber keyword."""
    from fontTools.ttLib import TTCollection, TTFont

    source = next((os.path.join(root, name)
                   for directory in font_dirs()
                   for root, _dirs, names in os.walk(directory)
                   for name in names if name.lower().endswith((".ttf", ".otf"))),
                  None)
    if source is None:
        pytest.skip("no standalone font available to build a TTC fixture")
    collection = TTCollection()
    collection.fonts = [TTFont(source)]
    path = tmp_path / "fixture.ttc"
    collection.save(path)
    font = Font("fixture", path=str(path))
    assert font.available, font.load_error


@pytest.mark.parametrize("stack", [hstack, vstack])
def test_stack_at_is_the_resulting_group_north_west(stack):
    a = Box(None, w=20, h=10, add=False)
    b = Box(None, w=10, h=30, add=False)
    result = stack([a, b], at=(100, 80))
    assert tuple(result.bbox.anchor("nw")) == pytest.approx((100, 80))


def test_stack_panel_at_includes_the_panel():
    result = hstack([Box("a", add=False), Box("b", add=False)],
                    at=(40, 50), pad=10)
    assert tuple(result.bbox.anchor("nw")) == pytest.approx((40, 50))


def test_max_w_reflows_and_breaks_an_unbreakable_label():
    box = Box("supercalifragilisticexpialidocious", max_w=80, add=False)
    assert box.bbox.w <= 80
    assert box.label.bbox.w <= box.bbox.w - 24 + 1e-9
    with Figure() as fig:
        fig.add(box)
    assert not fig.audit().by_kind("overflow")


def test_self_loop_remains_live_after_move_and_resize():
    state = Box("state", w=80, h=40, add=False)
    loop = self_loop(state, add=False)
    before = loop.bbox
    state.move(120, 50)
    moved = loop.bbox
    assert (moved.x - before.x, moved.y - before.y) == pytest.approx((120, 50))
    state.resize(160, 80)
    assert loop.endpoints()[0][0] == state.uv(0.275, 0).point


def test_clip_data_does_not_clip_axis_text():
    frame = Frame(0, 0, 100, 60, clip_data=True, add=False)
    frame.line([-1, 2], [0.5, 0.5])
    frame.axes(xlabel="outside x", ylabel="outside y")
    svg = frame.render(RenderContext()).render()
    assert "clip-path" in svg
    clipped_groups = re.findall(r'<g clip-path="[^"]+">(.*?)</g>', svg, re.S)
    assert clipped_groups
    assert all("outside x" not in group and "outside y" not in group
               for group in clipped_groups)


@pytest.mark.parametrize("suffix", ["jpg", "jpeg", "webp"])
def test_unsupported_raster_extensions_are_rejected(tmp_path, suffix):
    with Figure() as fig:
        Box("not a disguised PNG")
    with pytest.raises(ExportError, match="not supported"):
        fig.save(tmp_path / f"figure.{suffix}")


def test_word_spacing_and_text_transform_affect_layout_and_svg():
    plain = Text("mixed case", text_align="left", add=False)
    styled = Text("mixed case", text_align="left", word_spacing=12,
                  text_transform="uppercase", add=False)
    assert styled.bbox.w > plain.bbox.w + 11
    assert ">MIXED CASE</text>" in styled.render(RenderContext()).render()


def test_unimplemented_font_variant_is_loud():
    with pytest.raises(UnknownProperty):
        Text("small caps", font_variant="small-caps", add=False)


@pytest.mark.parametrize("factory, pattern", [
    (lambda: connect((0, 0), (10, 0), route="curv", add=False), "curve"),
    (lambda: Marker((0, 0), shape="circel", add=False), "circle"),
    (lambda: Vector([1], orient="diagonal", add=False), "orient"),
    (lambda: ColorBar(orient="diagonal", add=False), "orient"),
    (lambda: Frame(xscale="logarithmic", add=False), "xscale"),
])
def test_invalid_string_options_raise_with_guidance(factory, pattern):
    with pytest.raises(ValueError, match=pattern):
        factory()


def test_grid_rejects_invalid_alignment_and_order():
    with pytest.raises(ValueError, match="align"):
        grid([Box(None, add=False)], align="centre")
    with pytest.raises(ValueError, match="order"):
        grid([Box(None, add=False)], order="diagonal")


def test_matrix_highlight_keeps_its_value_in_front():
    matrix = Matrix([[1]], show_values=True, value_fmt="{}", add=False)
    cell = matrix.cell(0, 0)
    label = matrix._value_labels[0]
    matrix.highlight(0, 0, fill="black")
    assert matrix.children.index(label) > matrix.children.index(cell)


def test_contrast_audit_uses_text_fill_alias_and_span_colours():
    with Figure(background="#000") as good:
        Text("white", fill="#fff")
    assert not good.audit().by_kind("contrast")

    with Figure(background="#fff") as bad:
        Text([Span("invisible", color="#fff")], color="#000")
    findings = bad.audit().by_kind("contrast")
    assert findings and findings[0].detail["color"] == "#fff"


@pytest.mark.parametrize("orient, dimension", [("v", "h"), ("h", "w")])
def test_colorbar_respects_declared_strip_bounds(orient, dimension):
    bar = ColorBar(w=75, h=120, orient=orient, labels=False, add=False)
    assert getattr(bar.bbox, dimension) == pytest.approx({"w": 75, "h": 120}[dimension])


def test_theme_accepts_a_dict_valued_fill():
    gradient = {"type": "linear", "stops": ["#fff", "#000"]}
    theme = Theme(fill=gradient)
    assert Box(None, theme=theme, add=False).prop("fill") == gradient


def test_math_overhang_is_included_and_normalized():
    text = Text("$j$", font_size=20, text_align="left", add=False)
    svg = text.render(RenderContext()).render()
    match = re.search(r'<path d="([^"]+)"', svg)
    if not match:
        pytest.skip("matplotlib mathtext is unavailable")
    x0, _y0, x1, _y1 = path_bbox(match.group(1))
    assert x0 == pytest.approx(text.bbox.x0, abs=0.001)
    assert x1 <= text.bbox.x1 + 0.001


def test_html_embed_option_has_defined_distinct_outputs():
    with Figure() as fig:
        Box("html")
    inline = fig.to_html(embed=True)
    image = fig.to_html(embed=False)
    assert inline != image
    assert "<svg" in inline
    assert 'src="data:image/svg+xml;base64,' in image


def test_rich_text_repr_uses_plain_text():
    assert "rich" in repr(Text(Span("rich"), add=False))


def test_rotate_is_a_common_element_constructor_option():
    box = Box(None, w=40, h=20, rotate=45, add=False)
    assert box.bbox.w == pytest.approx(42.4264, abs=0.001)
    assert box.bbox.h == pytest.approx(42.4264, abs=0.001)


def _box_tuple(bb):
    return (bb.x, bb.y, bb.w, bb.h)


@pytest.mark.parametrize("shape", [Box, Pill, Ellipse, Diamond])
def test_constructor_rotate_matches_rotating_afterwards(shape):
    """A subclass has not sized itself when Element.__init__ runs, so applying
    the rotation there pivoted on the placeholder box and landed the element
    somewhere that depended on how long its label was."""
    after = shape("A considerably longer label", add=False)
    after.rotate(45)
    at_construction = shape("A considerably longer label", rotate=45,
                            add=False)
    assert _box_tuple(at_construction.bbox) == pytest.approx(
        _box_tuple(after.bbox))


def test_constructor_rotate_matches_for_groups_too():
    def pair():
        return [Box("hi", 0, 0, 40, 20, add=False),
                Box("there", 60, 0, 40, 20, add=False)]

    after = Group(*pair(), add=False)
    after.rotate(30)
    at_construction = Group(*pair(), rotate=30, add=False)
    assert _box_tuple(at_construction.bbox) == pytest.approx(
        _box_tuple(after.bbox))


def test_constructor_rotate_about_takes_an_explicit_pivot():
    after = Box("Encoder block", add=False)
    after.rotate(90, about=(0, 0))
    at_construction = Box("Encoder block", rotate=90, rotate_about=(0, 0),
                          add=False)
    assert _box_tuple(at_construction.bbox) == pytest.approx(
        _box_tuple(after.bbox))
