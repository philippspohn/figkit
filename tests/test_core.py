import pytest

from figkit import Box, Figure, Group, Point, Text, arrow
from figkit.core import Anchor


def mk(w=40, h=20, **kw):
    return Box(None, 0, 0, w, h, add=False, **kw)


def test_anchors_are_live():
    b = mk()
    a = b.e
    assert isinstance(a, Anchor)
    assert a.point == (40, 10)
    b.move(100, 0)
    assert a.point == (140, 10)


def test_anchor_offsets():
    b = mk()
    assert (b.e + (5, 0)).point == (45, 10)
    assert b.e.offset(0, -3).point == (40, 7)
    assert (b.center - (10, 10)).point == (10, 0)


def test_anchor_normals_point_outward():
    b = mk()
    assert b.n.normal == (0, -1)
    assert b.e.normal == (1, 0)
    assert b.uv(0, 0.5).normal == (-1, 0)


def test_at_angle_is_on_the_border():
    b = mk(100, 40)
    for deg in (0, 45, 90, 180, 270):
        assert b.bbox.contains(b.at_angle(deg).point)


def test_element_used_as_point_is_its_centre():
    from figkit.geom import to_point
    b = mk()
    assert to_point(b) == b.bbox.center


def test_group_bbox_follows_children():
    a, b = mk(), mk().right_of(mk(), gap=50)
    g = Group(a, b, add=False)
    assert g.bbox.w > 40
    b.move(0, 100)
    assert g.bbox.h > 100


def test_group_move_moves_children():
    a = mk()
    g = Group(a, add=False)
    g.move(10, 20)
    assert a.bbox.anchor("nw") == (10, 20)


def test_reparenting_removes_from_old_parent():
    g1, g2 = Group(add=False), Group(add=False)
    b = mk()
    g1.add(b)
    g2.add(b)
    assert b.parent is g2
    assert len(g1) == 0


def test_remove_and_clear():
    b = mk()
    g = Group(b, add=False)
    g.remove_child(b)
    assert b.parent is None and len(g) == 0


def test_group_cannot_contain_itself():
    g = Group(add=False)
    with pytest.raises(ValueError):
        g.add(g)


def test_hidden_children_are_excluded():
    a, b = mk(), mk().at(500, 0)
    g = Group(a, b, add=False)
    wide = g.bbox.w
    b.hide()
    assert g.bbox.w < wide


def test_rotation_updates_bbox_and_anchors():
    b = mk(100, 20)
    b.rotate(90)
    assert b.bbox.w == pytest.approx(20)
    assert b.bbox.h == pytest.approx(100)


def test_move_after_rotation_is_still_world_space():
    b = mk(100, 20).at(0, 0)
    b.rotate(90)
    before = b.bbox.anchor("nw")
    b.move(30, -10)
    assert b.bbox.anchor("nw") == pytest.approx((before.x + 30, before.y - 10))


def test_scale_about_a_point():
    b = mk(10, 10).at(0, 0)
    b.scale_by(2, about=(0, 0))
    assert b.bbox == (0, 0, 20, 20)


def test_resize_keeps_anchor_fixed():
    b = mk(40, 20).at(100, 100)
    b.resize(w=80, anchor="center")
    assert b.bbox.center.x == pytest.approx(120)
    b2 = mk(40, 20).at(100, 100)
    b2.resize(w=80, anchor="nw")
    assert b2.bbox.anchor("nw") == (100, 100)


def test_copy_is_independent():
    a = Box("hello", add=False).at(10, 10)
    b = a.copy()
    b.move(100, 0)
    assert a.bbox.x0 == 10
    assert b.bbox.x0 == 110
    assert b.parent is None


def test_span_x_stretches_between():
    a = mk().at(0, 0)
    b = mk().at(200, 0)
    bar = mk(10, 4).span_x(a, b)
    assert bar.bbox.x0 == pytest.approx(0)
    assert bar.bbox.x1 == pytest.approx(240)


def test_named_lookup():
    with Figure() as fig:
        Box("x", name="target")
    assert fig.find("target") is not None
    assert fig.find("nope") is None


def test_ink_bbox_includes_stroke():
    b = mk(stroke="#000", stroke_width=4)
    assert b.ink_bbox.w == pytest.approx(b.bbox.w + 4)
    plain = mk(stroke="none")
    assert plain.ink_bbox.w == plain.bbox.w


def test_restyle_merges():
    b = Box("x", fill="red", add=False)
    b.restyle(stroke="blue")
    assert b.prop("fill") == "red" and b.prop("stroke") == "blue"


def test_invalidate_recomputes_size():
    b = Box("hi", add=False)
    w = b.bbox.w
    b.restyle(font_size=40)
    assert b.bbox.w > w


def test_text_setter_resizes_box():
    b = Box("hi", add=False)
    w = b.bbox.w
    b.text = "a considerably longer label"
    assert b.bbox.w > w


def test_auto_add_only_inside_a_figure():
    loose = Box("x", add=False)
    assert loose.parent is None
    with Figure() as fig:
        inside = Box("y")
    assert inside.parent is fig


def test_ambient_state_is_per_context():
    """Two concurrent tasks must not steal each other's elements."""
    import asyncio

    from figkit import Style, use_theme
    from figkit.style import current_theme

    async def build(fill, hold):
        theme = Figure().theme.derive(box=Style(fill=fill))
        with Figure(theme=theme) as fig:
            with use_theme(theme):
                await asyncio.sleep(hold)
                box = Box("x")
                await asyncio.sleep(hold)
        return fig, box, current_theme()

    async def main():
        return await asyncio.gather(build("#111111", 0.01),
                                    build("#222222", 0.005))

    (fig_a, box_a, _), (fig_b, box_b, _) = asyncio.run(main())
    assert fig_a.children == [box_a]          # no cross-contamination
    assert fig_b.children == [box_b]
    assert box_a.prop("fill") == "#111111"
    assert box_b.prop("fill") == "#222222"


def test_theme_context_restores_on_exit():
    from figkit import DEFAULT_THEME, use_theme
    from figkit.style import current_theme

    assert current_theme() is DEFAULT_THEME
    other = DEFAULT_THEME.derive(radius=99)
    with use_theme(other):
        assert current_theme() is other
    assert current_theme() is DEFAULT_THEME
