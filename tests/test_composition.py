"""Components, baseline rows and the higher-level figure idioms."""

import pytest

from figkit import (Box, Component, Dot, Figure, LabelledMatrix, Matrix, Point,
                    Text, arrow, baseline_of, brace_around, hstack, self_loop)


class PortBlock(Component):
    def build(self, label, w=120):
        body = Box(label, w=w)
        dot = Dot(body.e, r=4)
        self.expose("port", dot.center)
        self.expose("body", body)
        return [body, dot]


# -- Component -------------------------------------------------------------

def test_component_exposes_named_anchors():
    with Figure() as fig:
        block = PortBlock("filter")
    assert set(block.exposed) == {"port", "body"}
    assert block.port.point == block.body.bbox.anchor("e")
    assert block.anchor("port").point == block.port.point


def test_exposed_anchors_stay_live():
    block = PortBlock("filter", add=False)
    before = block.port.point
    block.move(0, 40)
    assert block.port.point == (before.x, before.y + 40)


def test_component_accepts_group_options_without_passing_them_to_build():
    block = PortBlock("filter", name="blk", z=3, add=False)
    assert block.name == "blk" and block.z == 3
    assert block.body.text == "filter"


def test_component_build_arguments_reach_build():
    assert PortBlock("filter", w=250, add=False).body.bbox.w == 250


def test_unknown_attribute_still_raises():
    block = PortBlock("x", add=False)
    with pytest.raises(AttributeError, match="no attribute 'nope'"):
        block.nope


def test_exposing_a_reserved_name_is_refused():
    class Bad(Component):
        def build(self):
            body = Box("x")
            self.expose("center", body.e)
            return [body]

    with pytest.raises(ValueError, match="reserved"):
        Bad(add=False)


def test_component_without_build_is_explicit_about_it():
    class Empty(Component):
        pass

    with pytest.raises(NotImplementedError, match="must implement build"):
        Empty(add=False)


def test_component_is_a_placeable_group():
    a = Box("a", add=False)
    block = PortBlock("b", add=False).right_of(a, gap=30)
    assert block.bbox.x0 == pytest.approx(a.bbox.x1 + 30)


# -- baseline rows ---------------------------------------------------------

def test_baseline_of_looks_through_shapes_and_groups():
    text = Text("hi", add=False)
    assert baseline_of(text) == text.first_baseline
    box = Box("hi", add=False)
    assert baseline_of(box) == box.label.first_baseline
    assert baseline_of(Matrix([[1]], add=False)) is None


def test_baseline_row_lines_up_text_baselines():
    small = Text("small", font_size=10, add=False)
    big = Text("BIG", font_size=28, add=False)
    hstack([small, big], gap=10, align="baseline")
    assert baseline_of(small) == pytest.approx(baseline_of(big), abs=0.01)


def test_baseline_row_centres_untexted_items_on_the_maths_axis():
    lhs = Text("$C =$", font_size=20, add=False)
    matrix = Matrix([[0.1, 0.2], [0.3, 0.4]], cell=20, add=False)
    hstack([lhs, matrix], gap=10, align="baseline")
    # the matrix centre sits above the baseline, not on it
    assert matrix.bbox.cy < baseline_of(lhs)
    assert matrix.bbox.cy > baseline_of(lhs) - 20


def test_baseline_row_falls_back_to_centring_without_any_text():
    a = Box(None, 0, 0, 20, 20, add=False)
    b = Box(None, 0, 0, 20, 60, add=False)
    hstack([a, b], gap=5, align="baseline")
    assert a.bbox.cy == pytest.approx(b.bbox.cy, abs=0.01)


# -- LabelledMatrix --------------------------------------------------------

def test_labelled_matrix_places_its_parts():
    lm = LabelledMatrix([[0.1, 0.2], [0.3, 0.4]], cell=20, row_label="rows",
                        col_label="cols", caption="$M$", add=False)
    assert lm.matrix.shape() == (2, 2)
    assert lm.col_text.bbox.y1 <= lm.matrix.bbox.y0
    assert lm.row_text.bbox.x1 <= lm.matrix.bbox.x0
    assert lm.caption_text.bbox.y0 >= lm.matrix.bbox.y1


def test_labelled_matrix_row_label_is_rotated():
    lm = LabelledMatrix([[1, 2], [3, 4]], cell=20, row_label="sequence length",
                        add=False)
    assert lm.row_text.bbox.h > lm.row_text.bbox.w      # reads bottom-to-top


@pytest.mark.parametrize("kind", ["square", "round"])
def test_labelled_matrix_brackets_surround_the_grid(kind):
    lm = LabelledMatrix([[1, 2], [3, 4]], cell=20, brackets=kind, add=False)
    assert lm.bbox.x0 < lm.matrix.bbox.x0
    assert lm.bbox.x1 > lm.matrix.bbox.x1


def test_labelled_matrix_moves_as_one_unit():
    lm = LabelledMatrix([[1, 2]], cell=20, caption="$M$", brackets="round",
                        add=False)
    before = lm.caption_text.bbox.x0
    lm.move(100, 0)
    assert lm.caption_text.bbox.x0 == pytest.approx(before + 100)


# -- loops and braces ------------------------------------------------------

@pytest.mark.parametrize("side,check", [
    ("top", lambda box, bb: bb.y0 < box.y0),
    ("bottom", lambda box, bb: bb.y1 > box.y1),
    ("left", lambda box, bb: bb.x0 < box.x0),
    ("right", lambda box, bb: bb.x1 > box.x1),
])
def test_self_loop_bulges_from_the_right_side(side, check):
    state = Box("s", w=80, h=40, add=False)
    loop = self_loop(state, side=side, size=30, add=False)
    assert check(state.bbox, loop.bbox)


def test_self_loop_starts_and_ends_on_the_element():
    state = Box("s", w=80, h=40, add=False)
    loop = self_loop(state, side="top", add=False)
    _d, start, _sd, end, _ed = loop.geometry()
    assert state.bbox.expand(1).contains(start)
    assert state.bbox.expand(1).contains(end)
    assert start.distance_to(end) > 1


def test_self_loop_rejects_a_bad_side():
    with pytest.raises(ValueError, match="use top/bottom"):
        self_loop(Box("s", add=False), side="diagonal", add=False)


def test_brace_around_spans_the_items():
    boxes = [Box(str(i), w=60, add=False).at(i * 90, 0) for i in range(3)]
    brace = brace_around(boxes, side="top", gap=10, label="all three",
                         add=False)
    assert brace.bbox.w >= boxes[-1].bbox.x1 - boxes[0].bbox.x0
    assert brace.bbox.y1 <= boxes[0].bbox.y0
    assert brace.label.text == "all three"


def test_brace_around_rejects_a_bad_side():
    with pytest.raises(ValueError, match="use top/bottom"):
        brace_around([Box("a", add=False)], side="inside")


def test_composition_figure_audits_clean():
    with Figure() as fig:
        lhs = Text("$C =$", font_size=18)
        lm = LabelledMatrix([[0.2, 0.8], [0.4, 0.1]], cell=18, brackets="round",
                            col_label="$d$")
        hstack([lhs, lm], gap=12, align="baseline")
        a = Box("idle", w=90).at(0, 160)
        b = Box("run", w=90).right_of(a, gap=60)
        arrow(a.e, b.w, label="go")
        self_loop(b, side="top", size=30, label="retry", head_size=8)
        brace_around([a, b], side="bottom", gap=30, label="run")
    assert not fig.audit(), str(fig.audit())
