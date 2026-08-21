import math
import re

import pytest

from figkit import (Box, Connector, Point, arrow, connect, curve,
                    double_arrow, elbow, line)
from figkit.svgdoc import RenderContext
from figkit.svgpath import abs_segments, path_bbox


def render(el):
    return el.render(RenderContext()).render()


@pytest.fixture
def pair():
    a = Box("A", w=60, h=30, add=False).at(0, 0)
    b = Box("B", w=60, h=30, add=False).at(200, 100)
    return a, b


def test_arrow_endpoints_hit_anchors(pair):
    a, b = pair
    ar = arrow(a.e, b.w, add=False)
    d, p0, _sd, p1, _ed = ar.geometry()
    assert p0 == a.e.point
    assert p1 == b.w.point


def test_arrow_follows_moved_element(pair):
    a, b = pair
    ar = arrow(a.e, b.w, add=False)
    before = ar.geometry()[3]
    b.move(50, 0)
    assert ar.geometry()[3].x == pytest.approx(before.x + 50)


def test_arrow_head_is_drawn_and_line_is_trimmed(pair):
    a, b = pair
    out = render(arrow(a.e, b.w, add=False))
    assert out.count("<path") == 2          # line + head
    plain = render(line(a.e, b.w, add=False))
    assert plain.count("<path") == 1


def test_head_none_and_double(pair):
    a, b = pair
    assert render(arrow(a.e, b.w, head="none", add=False)).count("<path") == 1
    assert render(double_arrow(a.e, b.w, add=False)).count("<path") == 3


@pytest.mark.parametrize("kind", ["triangle", "stealth", "open", "circle",
                                  "diamond", "square", "bar", "cross"])
def test_all_head_kinds_render(pair, kind):
    a, b = pair
    out = render(arrow(a.e, b.w, head=kind, add=False))
    assert "<path" in out or "<ellipse" in out


def test_unknown_head_raises(pair):
    a, b = pair
    with pytest.raises(ValueError):
        render(arrow(a.e, b.w, head="banana", add=False))


def test_element_endpoints_pick_a_border_point(pair):
    a, b = pair
    _d, p0, _sd, p1, _ed = arrow(a, b, add=False).geometry()
    assert a.bbox.contains(p0)
    assert b.bbox.contains(p1)


def test_elbow_is_axis_aligned(pair):
    a, b = pair
    el = elbow(a.e, b.w, stub=12, corner=0, add=False)
    segs = [s for s in abs_segments(el.path_data()) if s[0] in ("M", "L")]
    pts = [Point(s[1], s[2]) for s in segs]
    for p, q in zip(pts, pts[1:]):
        assert abs(p.x - q.x) < 1e-6 or abs(p.y - q.y) < 1e-6


def test_elbow_honours_stub(pair):
    a, b = pair
    el = elbow(a.e, b.w, stub=25, corner=0, add=False)
    segs = abs_segments(el.path_data())
    first, second = Point(segs[0][1], segs[0][2]), Point(segs[1][1], segs[1][2])
    assert first.distance_to(second) == pytest.approx(25, abs=0.01)


def test_elbow_rounding_produces_curves(pair):
    a, b = pair
    assert "Q" in elbow(a.e, b.w, corner=8, add=False).path_data()
    assert "Q" not in elbow(a.e, b.w, corner=0, add=False).path_data()


def test_curve_bend_follows_anchor_normals():
    a = Box("A", w=60, h=30, add=False).at(0, 0)
    b = Box("B", w=60, h=30, add=False).at(200, 0)
    flat = curve(a.s, b.s, bend=0.0, add=False)
    deep = curve(a.s, b.s, bend=0.6, add=False)
    # both anchors face south, so a bigger bend must dip further down
    assert path_bbox(deep.path_data())[3] > path_bbox(flat.path_data())[3]


def test_curve_bow_flips_sides():
    left = curve((0, 0), (100, 0), bow=0.5, add=False)
    right = curve((0, 0), (100, 0), bow=-0.5, add=False)
    assert path_bbox(left.path_data())[1] < 0        # bows up (left of travel)
    assert path_bbox(right.path_data())[3] > 0       # bows down


def test_waypoints_are_visited():
    c = connect((0, 0), (100, 0), route="curve", waypoints=[(50, -60)],
                add=False)
    assert path_bbox(c.path_data())[1] < -30


def test_connector_label_sits_near_the_path(pair):
    a, b = pair
    ar = arrow(a.e, b.w, label="loss", add=False)
    assert ar.label.text == "loss"
    mid = ar.point_at(0.5)
    assert ar.label.bbox.center.distance_to(mid) < 40
    assert "loss" in render(ar)


def test_point_at_and_length(pair):
    a, b = pair
    ar = arrow(a.e, b.w, add=False)
    assert ar.point_at(0.0).distance_to(a.e.point) < 1e-6
    assert ar.point_at(1.0).distance_to(b.w.point) < 1e-6
    assert ar.length == pytest.approx(a.e.point.distance_to(b.w.point))


def test_gap_pulls_endpoints_back(pair):
    a, b = pair
    plain = arrow(a.e, b.w, add=False).geometry()[1]
    gapped = arrow(a.e, b.w, gap=10, add=False).geometry()[1]
    assert gapped.distance_to(plain) == pytest.approx(10)


def test_connector_bbox_covers_path(pair):
    a, b = pair
    el = elbow(a.e, b.w, add=False)
    x0, y0, x1, y1 = path_bbox(el.path_data())
    bb = el.bbox
    assert bb.x0 <= x0 + 1e-6 and bb.x1 >= x1 - 1e-6
    assert bb.y0 <= y0 + 1e-6 and bb.y1 >= y1 - 1e-6


def test_side_hint_forces_an_edge(pair):
    a, b = pair
    _d, p0, _sd, _p1, _ed = arrow(a, b, start_side="top", add=False).geometry()
    assert p0.y == pytest.approx(a.bbox.y0)


def _head_axis_offset(conn) -> float:
    """Perpendicular distance from the stroke's end to the head's axis.

    A stroke that ends off the head's axis pokes out of its side once the
    stroke has any width — which is what trimming by arc length while aiming
    the head along the tangent at the tip used to do on curved paths.
    """
    from figkit.svgpath import flatten_path
    paths = re.findall(r'<path d="([^"]+)"', render(conn))
    end = Point(*flatten_path(paths[0], 12)[-1][-1])
    head = [Point(*p) for p in flatten_path(paths[1], 1)[0]]
    tip, back = head[0], head[1].lerp(head[2], 0.5)
    axis = (tip - back).normalized()
    v = end - tip
    return abs(v.x * axis.y - v.y * axis.x)


@pytest.mark.parametrize("kw", [
    dict(route="straight"),
    dict(route="curve", bow=0.3),
    dict(route="curve", bow=0.9),
    dict(route="curve", bow=-0.8),
    dict(route="elbow", stub=20),
    dict(route="curve", bow=0.7, stroke_width=6),
    dict(route="arc", bend=0.6),
])
def test_stroke_ends_on_the_head_axis(kw):
    conn = Connector((0, 0), (40, 110), head_size=16, add=False, **kw)
    assert _head_axis_offset(conn) < 0.05


def test_tail_head_is_aimed_too():
    conn = Connector((0, 0), (40, 110), route="curve", bow=0.9, head="none",
                     tail="triangle", head_size=16, add=False)
    paths = re.findall(r'<path d="([^"]+)"', render(conn))
    assert len(paths) == 2                       # stroke + tail head only


def test_head_points_along_the_path_not_across_it():
    """The head axis should follow the direction the stroke arrives from."""
    from figkit.svgpath import flatten_path
    conn = curve((0, 0), (40, 110), bow=0.9, head_size=16, add=False)
    paths = re.findall(r'<path d="([^"]+)"', render(conn))
    stroke_end = Point(*flatten_path(paths[0], 8)[-1][-1])
    tip = conn.geometry()[3]
    axis = (tip - stroke_end).normalized()
    assert axis.dot(conn.direction_at(1.0)) > 0.9        # near-parallel
