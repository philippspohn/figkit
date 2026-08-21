import math

import pytest

from figkit.geom import Affine
from figkit.mathtext import MathError, math_available, render_math
from figkit.svgpath import (abs_segments, flatten_path, parse_path, path_bbox,
                            path_length, point_at, rounded_polyline,
                            transform_path_data)


def test_parse_expands_repeated_coordinates():
    assert parse_path("M0 0 10 10") == [("M", [0, 0]), ("L", [10, 10])]
    assert len(parse_path("L1 1 2 2 3 3")) == 3


def test_relative_commands_become_absolute():
    segs = abs_segments("m10 10 l5 0 v5 h-5 z")
    assert segs[0] == ("M", 10, 10)
    assert segs[1] == ("L", 15, 10)
    assert segs[2] == ("L", 15, 15)
    assert segs[3] == ("L", 10, 15)
    assert segs[4] == ("Z",)


def test_shorthand_curves_reflect_control_points():
    segs = abs_segments("M0 0 C0 10 10 10 10 0 S20 -10 20 0")
    assert segs[-1][0] == "C"
    assert segs[-1][1] == pytest.approx(10)   # reflected control x
    assert segs[-1][2] == pytest.approx(-10)


def test_arc_is_converted_to_cubics():
    segs = abs_segments("M0 0 A10 10 0 0 1 20 0")
    assert all(s[0] in ("M", "C") for s in segs)
    x0, y0, x1, y1 = path_bbox("M0 0 A10 10 0 0 1 20 0")
    assert x1 == pytest.approx(20)
    # sweep-flag=1 is clockwise in SVG's y-down space, so the arc bulges up
    assert y0 == pytest.approx(-10, abs=0.05)


def test_bbox_uses_curve_extrema_not_control_points():
    # control points reach y=100 but the curve only reaches y=75
    assert path_bbox("M0 0 C0 100 100 100 100 0")[3] == pytest.approx(75, abs=1e-6)


def test_transform_roundtrip():
    d = "M0 0 L10 10 Q20 0 30 10"
    m = Affine.translate(5, 5) @ Affine.scale(2)
    moved = transform_path_data(d, m)
    back = transform_path_data(moved, m.inverse())
    assert path_bbox(back) == pytest.approx(path_bbox(d), abs=1e-6)


def test_flatten_and_length():
    assert path_length("M0 0 L30 40") == pytest.approx(50)
    polys = flatten_path("M0 0 L10 0 M20 0 L30 0")
    assert len(polys) == 2


def test_point_at_walks_the_path():
    p, d = point_at("M0 0 L100 0", 0.5)
    assert p.x == pytest.approx(50, abs=0.5)
    assert d.x == pytest.approx(1, abs=1e-6)


def test_rounded_polyline_skips_collinear_corners():
    straight = rounded_polyline([(0, 0), (50, 0), (100, 0)], radius=8)
    assert "Q" not in straight
    corner = rounded_polyline([(0, 0), (50, 0), (50, 50)], radius=8)
    assert corner.count("Q") == 1


def test_rounded_radius_is_clamped():
    d = rounded_polyline([(0, 0), (10, 0), (10, 10)], radius=999)
    x0, y0, x1, y1 = path_bbox(d)
    assert x1 <= 10 + 1e-6 and y1 <= 10 + 1e-6


@pytest.mark.skipif(not math_available(), reason="needs matplotlib")
class TestMath:
    def test_renders_outlines_with_metrics(self):
        r = render_math("x^2", 20)
        assert r.d.startswith("M")
        assert r.width > 0
        assert r.ascent > 0

    def test_scales_with_size(self):
        small = render_math("x", 10)
        big = render_math("x", 20)
        assert big.width == pytest.approx(small.width * 2, rel=0.02)

    def test_baseline_at_origin(self):
        r = render_math("x", 20)
        x0, y0, x1, y1 = path_bbox(r.d)
        assert y1 <= 0.5           # sits above the baseline
        assert -y0 == pytest.approx(r.ascent, abs=0.5)

    def test_descenders_go_below_baseline(self):
        assert render_math("y", 20).descent > 0

    def test_complex_expression(self):
        r = render_math(r"\sum_{i=1}^{n} \frac{\phi_i}{\tau}", 16)
        assert r.width > 25
        assert r.ascent > 10 and r.descent > 5

    def test_bad_expression_raises(self):
        with pytest.raises(MathError):
            render_math(r"\frac{", 12)
