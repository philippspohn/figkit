"""The audit has two jobs: catch real mistakes, and stay quiet otherwise.

The second is the harder one — a checker that cries wolf on every nested
label is worse than no checker at all — so the "intentional" half of this
file matters more than the "catches it" half.
"""

import pytest

from figkit import (Box, Circle, Dot, Figure, Group, Image, Legend, Marker,
                    Matrix, Panel, Polygon, Style, Text, Vector, arrow, curve,
                    elbow, fit, hstack, line)


# ==========================================================================
# It catches the things that actually go wrong
# ==========================================================================

def test_catches_partial_overlap_of_labelled_boxes():
    with Figure() as fig:
        Box("first", w=120, h=40).at(0, 0)
        Box("second", w=120, h=40).at(60, 20)
    report = fig.audit()
    assert report
    assert report.by_kind("overlap")


def test_catches_a_box_dropped_onto_a_matrix():
    with Figure() as fig:
        Matrix([[0.2, 0.8], [0.5, 0.1]], cell=30)
        Box("loss", w=120, h=40).at(30, 20)
    assert fig.audit().by_kind("overlap")


def test_catches_a_filled_box_painted_over_content():
    with Figure() as fig:
        cover = Box(None, 0, 0, 200, 40, fill="#eeeeee")
        Text("hidden text").at(10, 10)
        cover.to_front()
    findings = fig.audit().by_kind("overlap")
    assert findings and "hiding it completely" in findings[0].message
    assert findings[0].severity == "error"


def test_catches_a_label_too_wide_for_its_box():
    with Figure() as fig:
        Box("a considerably longer label than will ever fit", w=90, wrap=False)
    findings = fig.audit().by_kind("overflow")
    assert findings and "horizontally" in findings[0].message


def test_catches_unreadable_text():
    with Figure() as fig:
        Box("invisible", w=120, fill="#f3f4f6", color="#eef0f2")
    findings = fig.audit().by_kind("contrast")
    assert findings and findings[0].detail["ratio"] < 2


def test_contrast_uses_the_page_background_when_there_is_no_fill():
    with Figure(background="#ffffff") as fig:
        Text("pale", color="#fafafa")
    assert fig.audit().by_kind("contrast")


def test_catches_an_arrow_through_an_unrelated_box():
    with Figure() as fig:
        a = Box("A", w=60)
        Box("in the way", w=90).right_of(a, gap=60)
        b = Box("B", w=60).right_of(fig.children[1], gap=60)
        arrow(a.e, b.w)
    findings = fig.audit().by_kind("crossing")
    assert findings and "in the way" in findings[0].message


def test_catches_degenerate_geometry():
    with Figure() as fig:
        a = Box("A", w=60)
        arrow(a.e, a.e)
    assert fig.audit().by_kind("degenerate")


def test_catches_content_outside_a_pinned_canvas():
    with Figure(w=200, h=100) as fig:
        Box("here", w=60).at(0, 0)
        Box("off", w=60).at(600, 0)
    findings = fig.audit().by_kind("offscreen")
    assert findings and "outside" in findings[0].message


def test_autosized_figures_are_never_offscreen():
    with Figure() as fig:
        Box("a").at(0, 0)
        Box("b").at(9000, 9000)
    assert not fig.audit().by_kind("offscreen")


# ==========================================================================
# It stays quiet about the things that are meant to look like that
# ==========================================================================

def test_quiet_about_a_label_inside_its_box():
    with Figure() as fig:
        Box("perfectly ordinary", w=200, h=60)
    assert not fig.audit()


def test_quiet_about_a_panel_behind_its_contents():
    with Figure() as fig:
        a = Box("a")
        b = Box("b").right_of(a, gap=20)
        fit(a, b, pad=16, label="stage")
    assert not fig.audit()


def test_quiet_about_an_element_nested_inside_another():
    with Figure() as fig:
        outer = Box(None, 0, 0, 200, 120)
        Box("inner", w=80, h=40).inside(outer, anchor="center")
    assert not fig.audit()


def test_quiet_about_adjacent_matrix_cells():
    with Figure() as fig:
        Matrix([[i * 0.1 for i in range(6)] for _ in range(6)], cell=18)
        Vector([0.2, 0.4, 0.6], cell=(40, 12)).at(200, 0)
    assert not fig.audit()


def test_quiet_about_arrows_touching_their_own_endpoints():
    with Figure() as fig:
        a = Box("A", w=80)
        b = Box("B", w=80).right_of(a, gap=90).below_of(a, gap=60)
        arrow(a.e, b.w)
        elbow(a.s, b.n, stub=14)
        curve(a.se, b.nw)
    assert not fig.audit()


def test_quiet_about_arrows_crossing_each_other():
    with Figure() as fig:
        a, b = Box("A", w=60).at(0, 0), Box("B", w=60).at(0, 200)
        c, d = Box("C", w=60).at(300, 0), Box("D", w=60).at(300, 200)
        arrow(a.e, d.w)
        arrow(b.e, c.w)
    assert not fig.audit()


def test_quiet_about_a_deliberately_overlapping_decoration():
    with Figure() as fig:
        Group(*[Polygon([(0, 0), (60 + i * 4, 10), (30, 50 + i * 3)],
                        fill="#dddddd") for i in range(8)])
    assert not fig.audit()


def test_quiet_about_backdrops_pushed_behind():
    with Figure() as fig:
        Box(None, 0, 0, 300, 120, fill="#f2f2f2", z=-1)   # declared backdrop
        Box("on top", w=120, h=40).at(20, 20)
        Text("also on top").at(20, 80)
    assert not fig.audit()


def test_quiet_about_a_dot_marking_a_node():
    with Figure() as fig:
        node = Circle(None, r=12, fill="#ffffff")
        Dot(node.center, r=5, fill="#c2600c")
    assert not fig.audit()


def test_quiet_about_stacks_legends_and_tables():
    with Figure() as fig:
        row = hstack([Box(f"item {i}", w=90) for i in range(4)], gap=16)
        Legend([("train", "#4C72B0"), ("val", "#DD8452")]).below_of(row, gap=30)
    assert not fig.audit()


@pytest.mark.parametrize("theme_name", ["paper", "slide", "dark", "soft",
                                        "minimal", "blueprint"])
def test_quiet_across_themes(theme_name):
    from figkit import get_theme
    with Figure(theme=get_theme(theme_name)) as fig:
        a = Box("Encoder", style="block", w=120)
        b = Box("Decoder", style="blue", w=120).right_of(a, gap=60)
        arrow(a.e, b.w, label="z")
    assert not fig.audit(), str(fig.audit())


# ==========================================================================
# Escape hatches and the report API
# ==========================================================================

def test_ignore_audit_silences_an_element():
    with Figure() as fig:
        Box("first", w=120, h=40).at(0, 0)
        second = Box("second", w=120, h=40).at(60, 20)
    assert fig.audit()
    second.ignore_audit()
    assert not fig.audit()


def test_audit_false_at_construction():
    with Figure() as fig:
        Box("first", w=120, h=40).at(0, 0)
        Box("second", w=120, h=40, audit=False).at(60, 20)
    assert not fig.audit()


def test_ignore_argument_and_check_switches():
    with Figure() as fig:
        Box("first", w=120, h=40).at(0, 0)
        second = Box("second", w=120, h=40).at(60, 20)
    assert not fig.audit(ignore=[second])
    assert not fig.audit(overlap=False)


def test_overlap_all_is_stricter_than_content():
    with Figure() as fig:
        Group(Polygon([(0, 0), (60, 0), (60, 60)], fill="#ddd"),
              Polygon([(20, 20), (80, 20), (80, 80)], fill="#ccc"))
    assert not fig.audit()
    assert fig.audit(overlap="all")


def test_report_protocol():
    with Figure() as fig:
        Box("a", w=100, h=40).at(0, 0)
        Box("b", w=100, h=40).at(50, 10)
    report = fig.audit()
    assert bool(report) and len(report) >= 1
    assert list(report) == report.findings
    assert "figkit audit" in str(report)
    assert report[0].where is not None
    with pytest.raises(AssertionError):
        report.raise_if_any()


def test_clean_report_is_falsy_and_says_so():
    with Figure() as fig:
        Box("fine")
    report = fig.audit()
    assert not report and len(report) == 0
    assert "no issues" in str(report)
    report.raise_if_any()          # does not raise


def test_one_problem_yields_one_finding():
    """A shape and its label must not both report the same collision."""
    with Figure() as fig:
        Box("label one", w=140, h=40).at(0, 0)
        Box("label two", w=140, h=40).at(70, 15)
    assert len(fig.audit().by_kind("overlap")) == 1


def test_hidden_elements_are_not_audited():
    with Figure() as fig:
        Box("first", w=120, h=40).at(0, 0)
        Box("second", w=120, h=40).at(60, 20).hide()
    assert not fig.audit()


def test_contrast_message_never_reads_as_passing():
    """A ratio just under the threshold must not print as the threshold."""
    with Figure() as fig:
        Box("borderline", w=140, fill="#ffffff", color="#959595")
    finding = fig.audit().by_kind("contrast")[0]
    assert "2.99:1 (want 3.00:1)" in finding.message


def test_raw_point_endpoints_count_as_connections():
    """An arrow aimed at a label by coordinates is not "passing through" it."""
    with Figure() as fig:
        label = Text("destination").at(100, 0)
        arrow((0, 9), (label.bbox.cx, label.bbox.cy))
    assert not fig.audit().by_kind("crossing")


def test_raw_point_endpoints_still_catch_real_crossings():
    with Figure() as fig:
        a = Box("A", w=60)
        Box("through", w=90).right_of(a, gap=60)
        b = Box("B", w=60).right_of(fig.children[1], gap=60)
        arrow((a.bbox.x1, a.bbox.cy), (b.bbox.x0, b.bbox.cy))
    assert fig.audit().by_kind("crossing")
