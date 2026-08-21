import os
import xml.etree.ElementTree as ET

import pytest

from figkit import (Box, Brace, Figure, Frame, Group, Legend, Panel, Table,
                    Text, arrow, available_backends, fit, nice_ticks)
from figkit.export import ExportError


def test_context_manager_auto_adds():
    with Figure() as fig:
        a = Box("a")
        b = Box("b").right_of(a, gap=10)
        arrow(a.e, b.w)
    assert len(fig.children) == 3


def test_group_takes_ownership_from_figure():
    with Figure() as fig:
        a, b = Box("a"), Box("b")
        g = Group(a, b)
    assert fig.children == [g]
    assert a.parent is g


def test_autosize_includes_padding():
    with Figure(pad=20) as fig:
        Box(None, 0, 0, 100, 50, stroke="none")
    vb = fig.viewbox()
    assert vb.w == pytest.approx(140)
    assert vb.h == pytest.approx(90)
    assert vb.x == pytest.approx(-20)


def test_fixed_size_and_explicit_viewbox():
    with Figure(w=500, h=300) as fig:
        Box(None, 0, 0, 10, 10)
    assert fig.viewbox().w == 500
    fig.set_viewbox(0, 0, 42, 24)
    assert fig.viewbox().w == 42
    fig.fit_contents(pad=0)
    assert fig.viewbox().w < 42


def test_svg_is_wellformed_and_has_viewbox():
    with Figure() as fig:
        b = Box("hello $x^2$")
        Text("caption").below_of(b, gap=8)
    svg = fig.to_svg()
    root = ET.fromstring(svg[svg.index("<svg"):])
    assert root.tag.endswith("svg")
    assert root.get("viewBox")


def test_z_order_sorting():
    with Figure() as fig:
        front = Box(None, 0, 0, 10, 10, z=5, name="front")
        back = Box(None, 0, 0, 10, 10, z=-5, name="back")
    svg = fig.to_svg()
    assert svg.index('data-name="back"') < svg.index('data-name="front"')


def test_to_front_and_to_back():
    with Figure() as fig:
        a, b = Box("a"), Box("b")
        a.to_front()
    assert fig.children[-1] is a
    b.to_back()
    assert fig.children[0] is b


def test_background_rect_is_emitted():
    with Figure(background="#ff0000") as fig:
        Box(None, 0, 0, 10, 10)
    assert 'fill="#ff0000"' in fig.to_svg()


def test_save_svg_and_html(tmp_path):
    with Figure() as fig:
        Box("hi")
    svg_path = fig.save(tmp_path / "f.svg")
    html_path = fig.save(tmp_path / "f.html")
    assert os.path.exists(svg_path) and os.path.exists(html_path)
    assert "<svg" in open(html_path).read()


def test_save_unknown_format_raises(tmp_path):
    with Figure() as fig:
        Box("hi")
    with pytest.raises(ExportError):
        fig.save(tmp_path / "f.xyz")


@pytest.mark.skipif(not available_backends()["cairosvg"],
                    reason="needs a raster backend")
def test_save_png_and_pdf(tmp_path):
    with Figure() as fig:
        Box("hi $\\alpha$")
    png = fig.save(tmp_path / "f.png", scale=2)
    pdf = fig.save(tmp_path / "f.pdf")
    assert open(png, "rb").read(8) == b"\x89PNG\r\n\x1a\n"
    assert open(pdf, "rb").read(4) == b"%PDF"


def test_embed_fonts_adds_font_face():
    from figkit.fonts import get_font
    if not get_font("sans-serif").available:
        pytest.skip("no font files on this machine")
    with Figure() as fig:
        Text("hello")
    assert "@font-face" in fig.to_svg(embed_fonts=True)


def test_theme_applies_through_figure():
    from figkit import DARK
    with Figure(theme=DARK) as fig:
        b = Box("hi", style="block")
    assert b.prop("fill") == DARK.styles["block"]["fill"]


# -- Frame -----------------------------------------------------------------

def test_frame_mapping_and_inverse():
    fr = Frame(0, 0, 200, 100, xlim=(0, 10), ylim=(0, 1), add=False)
    assert fr.pt(0, 0) == (0, 100)
    assert fr.pt(10, 1) == (200, 0)
    assert fr.pt(5, 0.5) == (100, 50)
    x, y = fr.data(100, 50)
    assert (x, y) == pytest.approx((5, 0.5))


def test_frame_move_carries_the_plot_area():
    fr = Frame(0, 0, 200, 100, add=False)
    fr.at(50, 25)
    assert fr.plot_area.anchor("nw") == (50, 25)
    assert fr.pt(0, 0) == (50, 125)


def test_frame_log_scale():
    fr = Frame(0, 0, 100, 100, xlim=(1, 1000), xscale="log", add=False)
    assert fr.px(1) == pytest.approx(0)
    assert fr.px(1000) == pytest.approx(100)
    assert fr.px(10) == pytest.approx(100 / 3, abs=0.01)


def test_frame_marks_are_elements():
    fr = Frame(0, 0, 200, 100, xlim=(0, 4), ylim=(0, 4), add=False)
    ln = fr.line([0, 1, 2], [0, 2, 4])
    assert ln.parent is fr
    assert ln.bbox.w == pytest.approx(100)
    bars = fr.bars([1, 2, 3], [1, 2, 3])
    assert len(bars.children) == 3


def test_frame_axes_and_ticks():
    fr = Frame(0, 0, 200, 100, xlim=(0, 10), ylim=(0, 1), add=False)
    ax = fr.axes(xlabel="x", ylabel="y", grid=True)
    assert len(list(ax.descendants())) > 5
    assert nice_ticks(0, 10, 5) == [0, 2, 4, 6, 8, 10]
    assert nice_ticks(0, 1, 4) == pytest.approx([0, 0.25, 0.5, 0.75, 1.0])


def test_frame_autoscale():
    fr = Frame(0, 0, 100, 100, add=False)
    fr.autoscale(xs=[0, 10], ys=[-1, 1], pad=0)
    assert fr.xlim == (0, 10)
    assert fr.ylim == (-1, 1)


# -- components ------------------------------------------------------------

def test_panel_tracks_targets():
    a = Box(None, 0, 0, 10, 10, stroke="none", add=False)
    p = Panel([a], pad=5, add=False)
    assert p.bbox == (-5, -5, 20, 20)
    a.move(100, 0)
    assert p.bbox.x0 == pytest.approx(95)


def test_panel_label_positions():
    a = Box(None, 0, 0, 100, 40, stroke="none", add=False)
    inside = Panel([a], pad=6, label="in", label_pos="nw", add=False)
    below = Panel([a], pad=6, label="under", label_pos="below", add=False)
    assert inside.label.bbox.y0 > inside.bbox.y0
    assert below.label.bbox.y0 >= below.bbox.y1 - 1e-6


def test_brace_spans_and_labels():
    br = Brace((0, 0), (100, 0), depth=12, label="group", add=False)
    assert br.bbox.w >= 100
    assert br.tip.y == pytest.approx(-12) or br.tip.y == pytest.approx(12)
    assert br.label.text == "group"


def test_table_shape_and_access():
    t = Table([["a", "b"], ["1", "2"], ["3", "4"]], add=False)
    assert len(t.cells) == 3 and len(t.cells[0]) == 2
    assert t.cell_text(2, 1).text == "4"
    assert t.cell(0, 0).bbox.w == t.cell(1, 0).bbox.w


def test_legend_has_one_row_per_entry():
    lg = Legend([("a", "#f00"), ("b", "#0f0"), ("c", "#00f")], add=False)
    assert len(lg.rows) == 3
    assert lg.bbox.h > 30
