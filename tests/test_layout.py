import pytest

from figkit import (Box, Figure, Group, Point, Spacer, align, between,
                    bbox_of, center_on, circular, distribute_h, distribute_v,
                    fit, grid, hstack, same_width, spread_h, vstack)


def mk(w=40, h=20, **kw):
    return Box(None, 0, 0, w, h, add=False, **kw)


def test_relative_placement_gaps_are_exact():
    a = mk()
    b = mk().right_of(a, gap=25)
    assert b.bbox.x0 == pytest.approx(a.bbox.x1 + 25)
    assert b.bbox.cy == pytest.approx(a.bbox.cy)

    c = mk().below_of(a, gap=10)
    assert c.bbox.y0 == pytest.approx(a.bbox.y1 + 10)

    d = mk().left_of(a, gap=5)
    assert d.bbox.x1 == pytest.approx(a.bbox.x0 - 5)

    e = mk().above_of(a, gap=7)
    assert e.bbox.y1 == pytest.approx(a.bbox.y0 - 7)


def test_placement_alignment_edges():
    a = mk(40, 60)
    top = mk(20, 10).right_of(a, gap=5, align="top")
    bottom = mk(20, 10).right_of(a, gap=5, align="bottom")
    assert top.bbox.y0 == pytest.approx(a.bbox.y0)
    assert bottom.bbox.y1 == pytest.approx(a.bbox.y1)
    left = mk(20, 10).below_of(a, gap=5, align="left")
    assert left.bbox.x0 == pytest.approx(a.bbox.x0)
    with pytest.raises(ValueError):
        mk().right_of(a, align="left")


def test_placement_dx_dy_offsets():
    a = mk()
    b = mk().right_of(a, gap=10, dx=3, dy=-4)
    assert b.bbox.x0 == pytest.approx(a.bbox.x1 + 13)
    assert b.bbox.cy == pytest.approx(a.bbox.cy - 4)


def test_at_and_anchor():
    b = mk(40, 20).at(100, 50, anchor="center")
    assert b.bbox.center == Point(100, 50)
    b.at(0, 0)
    assert b.bbox.anchor("nw") == Point(0, 0)
    b.at((7, 8))
    assert b.bbox.anchor("nw") == Point(7, 8)


def test_inside_places_within_padding():
    outer = mk(200, 100)
    inner = mk(20, 10).inside(outer, anchor="nw", pad=8)
    assert inner.bbox.x0 == pytest.approx(outer.bbox.x0 + 8)
    assert inner.bbox.y0 == pytest.approx(outer.bbox.y0 + 8)


def test_align_batch():
    items = [mk(30, 10).at(0, 0), mk(30, 20).at(50, 33), mk(30, 5).at(90, 77)]
    align(items, "top")
    assert len({round(i.bbox.y0, 6) for i in items}) == 1
    align(items, "center_x")
    assert len({round(i.bbox.cx, 6) for i in items}) == 1
    with pytest.raises(ValueError):
        align(items, "diagonal")


def test_distribute_and_spread():
    items = [mk(30, 10), mk(50, 10), mk(20, 10)]
    distribute_h(items, gap=15, start=0)
    assert items[0].bbox.x0 == 0
    assert items[1].bbox.x0 == pytest.approx(45)
    assert items[2].bbox.x0 == pytest.approx(110)

    spread_h(items, 0, 300)
    gaps = [items[i + 1].bbox.x0 - items[i].bbox.x1 for i in range(2)]
    assert gaps[0] == pytest.approx(gaps[1])
    assert items[-1].bbox.x1 == pytest.approx(300)


def test_distribute_v():
    items = [mk(10, 30), mk(10, 10)]
    distribute_v(items, gap=5, start=100)
    assert items[0].bbox.y0 == 100
    assert items[1].bbox.y0 == pytest.approx(135)


def test_hstack_returns_movable_group():
    a, b, c = mk(), mk(60), mk(20, 40)
    row = hstack([a, b, c], gap=10, align="top")
    assert row.bbox.w == pytest.approx(40 + 60 + 20 + 20)
    before = a.bbox.x0
    row.move(100, 0)
    assert a.bbox.x0 == pytest.approx(before + 100)
    assert row.bbox.x0 == pytest.approx(before + 100)


def test_vstack_alignment():
    items = [mk(30, 10), mk(70, 10)]
    vstack(items, gap=6, align="left")
    assert items[0].bbox.x0 == pytest.approx(items[1].bbox.x0)
    assert items[1].bbox.y0 == pytest.approx(items[0].bbox.y1 + 6)


def test_grid_rows_and_cols():
    items = [mk(20, 20) for _ in range(6)]
    g = grid(items, cols=3, gap=10)
    assert g.bbox.w == pytest.approx(3 * 20 + 2 * 10)
    assert g.bbox.h == pytest.approx(2 * 20 + 1 * 10)
    assert items[3].bbox.y0 == pytest.approx(items[0].bbox.y1 + 10)


def test_fit_wraps_and_tracks():
    a, b = mk(), mk().right_of(mk(), gap=30)
    f = fit(a, b, pad=10)
    assert f.panel.bbox.x0 <= a.bbox.x0 - 10 + 1e-9
    a.move(0, 200)
    assert f.panel.bbox.h >= 200


def test_fit_panel_is_behind():
    a = mk()
    f = fit(a, pad=5)
    assert f.children[0] is f.panel
    assert f.panel.z < 0


def test_between_and_center_on():
    a = mk().at(0, 0)
    b = mk().at(100, 100)
    assert between(a, b) == Point(a.bbox.cx / 2 + b.bbox.cx / 2,
                                  a.bbox.cy / 2 + b.bbox.cy / 2)
    c = mk()
    center_on(c, b)
    assert c.bbox.center == b.bbox.center


def test_same_width_and_bbox_of():
    items = [mk(10), mk(90), mk(30)]
    same_width(items)
    assert all(i.bbox.w == 90 for i in items)
    assert bbox_of(items).w >= 90


def test_circular_places_on_radius():
    items = [mk(10, 10) for _ in range(4)]
    circular(items, center=(0, 0), radius=100)
    for it in items:
        assert it.bbox.center.length == pytest.approx(100, abs=1e-6)


def test_spacer_takes_space_but_draws_nothing():
    from figkit.svgdoc import RenderContext
    s = Spacer(50, 10, add=False)
    assert s.bbox.w == 50
    assert s.render(RenderContext()) is None
