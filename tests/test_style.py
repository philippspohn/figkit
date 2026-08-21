import pytest

from figkit import Box, Style, Theme, use_theme
from figkit.style import DEFAULT_THEME, normalize_dash


def test_style_aliases_and_flags():
    s = Style(bg="red", border_width=2, bold=True, dash="dashed", align="left")
    assert s["fill"] == "red"
    assert s["stroke_width"] == 2
    assert s["font_weight"] == "bold"
    assert s["stroke_dash"] == "6 4"
    assert s["text_align"] == "left"


def test_style_merge_right_wins():
    a = Style(fill="red", stroke="black")
    b = Style(fill="blue")
    assert (a | b)["fill"] == "blue"
    assert (a | b)["stroke"] == "black"
    assert a["fill"] == "red"          # immutability


def test_style_is_immutable():
    s = Style(fill="red")
    with pytest.raises(AttributeError):
        s.fill = "blue"


def test_dash_presets():
    assert normalize_dash("dotted") == "1.5 3"
    assert normalize_dash(True) == "6 4"
    assert normalize_dash([4, 2]) == "4 2"
    assert normalize_dash("solid") is None


def test_theme_role_beats_base():
    t = Theme(fill="#eee", box=Style(fill="#fff"))
    assert t.lookup("fill", "box") == ("#fff", True)
    assert t.lookup("fill", "text") == ("#eee", True)
    assert t.lookup("nothing", "box") == (None, False)


def test_theme_derive_inherits():
    t = DEFAULT_THEME.derive(radius=99)
    assert t.lookup("radius", "text")[0] == 99
    assert t.styles["blue"] == DEFAULT_THEME.styles["blue"]


def test_element_resolves_through_cascade():
    t = Theme(DEFAULT_THEME, box=Style(fill="#123456"))
    b = Box("hi", theme=t, add=False)
    assert b.prop("fill") == "#123456"
    assert Box("hi", theme=t, fill="#abcdef", add=False).prop("fill") == "#abcdef"


def test_palette_tokens_resolve():
    t = Theme(DEFAULT_THEME, palette={"brand": "#ff0000"})
    b = Box("hi", theme=t, fill="@brand", add=False)
    assert b.prop("fill") == "#ff0000"


def test_group_cascades_inherited_props_only():
    from figkit import Group
    g = Group(style=Style(font_size=30, fill="#ff0000"), add=False)
    b = Box("hi", add=False)
    g.add(b)
    assert b.prop("font_size") == 30           # inherited
    assert b.prop("fill") != "#ff0000"         # not inherited


def test_ambient_theme_context():
    t = DEFAULT_THEME.derive(box=Style(fill="#0f0f0f"))
    with use_theme(t):
        b = Box("x", add=False)
    assert b.prop("fill") == "#0f0f0f"


def test_named_style_lookup():
    b = Box("x", style="blue", add=False)
    assert b.prop("fill") == DEFAULT_THEME.styles["blue"]["fill"]
    with pytest.raises(KeyError):
        Box("x", style="does-not-exist", add=False)
