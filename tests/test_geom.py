import math

import pytest

from figkit.geom import Affine, BBox, Point, to_point


def test_point_arithmetic():
    p = Point(3, 4)
    assert p.length == 5
    assert p + (1, 1) == Point(4, 5)
    assert (p - Point(3, 4)).length == 0
    assert p * 2 == Point(6, 8)
    assert tuple(p) == (3.0, 4.0)
    assert p.lerp((13, 4), 0.5) == Point(8, 4)
    assert p.normalized().length == pytest.approx(1.0)


def test_point_rotation_and_angle():
    p = Point(1, 0).rotated(90)
    assert p.x == pytest.approx(0, abs=1e-9)
    assert p.y == pytest.approx(1)
    assert Point(0, 0).angle_to((1, 0)) == pytest.approx(0)
    assert Point(0, 0).angle_to((0, 1)) == pytest.approx(90)


def test_to_point_accepts_many_shapes():
    assert to_point((1, 2)) == Point(1, 2)
    assert to_point([1, 2]) == Point(1, 2)
    assert to_point(Point(1, 2)) == Point(1, 2)
    with pytest.raises(TypeError):
        to_point("nope")


def test_bbox_anchors():
    bb = BBox(10, 20, 100, 50)
    assert bb.center == Point(60, 45)
    assert bb.anchor("nw") == Point(10, 20)
    assert bb.anchor("se") == Point(110, 70)
    assert bb.anchor("n") == Point(60, 20)
    assert bb.anchor("e") == Point(110, 45)
    assert bb.uv(0.5, 1.0) == Point(60, 70)
    with pytest.raises(KeyError):
        bb.anchor("nowhere")


def test_bbox_at_angle_lands_on_border():
    bb = BBox(0, 0, 100, 40)
    for deg in range(0, 360, 7):
        p = bb.at_angle(deg)
        on_x = abs(p.x - bb.x0) < 1e-6 or abs(p.x - bb.x1) < 1e-6
        on_y = abs(p.y - bb.y0) < 1e-6 or abs(p.y - bb.y1) < 1e-6
        assert on_x or on_y
        assert bb.contains(p)


def test_bbox_union_expand_intersection():
    a = BBox(0, 0, 10, 10)
    b = BBox(20, 5, 10, 10)
    assert a.union(b) == BBox(0, 0, 30, 15)
    assert a.expand(5) == BBox(-5, -5, 20, 20)
    assert a.expand((1, 2)) == BBox(-2, -1, 14, 12)
    assert a.intersection(b) is None
    assert a.intersection(BBox(5, 5, 10, 10)) == BBox(5, 5, 5, 5)


def test_affine_compose_and_inverse():
    m = Affine.translate(10, 5) @ Affine.scale(2)
    assert m.apply((1, 1)) == Point(12, 7)
    assert m.inverse().apply(m.apply((3, 4))) == Point(3, 4)
    r = Affine.rotate(90, (0, 0))
    got = r.apply((1, 0))
    assert (got.x, got.y) == (pytest.approx(0, abs=1e-9), pytest.approx(1))
    assert Affine.IDENTITY.is_identity


def test_affine_bbox_rotation():
    bb = BBox(0, 0, 10, 20)
    out = Affine.rotate(90, bb.center).apply_bbox(bb)
    assert out.w == pytest.approx(20)
    assert out.h == pytest.approx(10)
