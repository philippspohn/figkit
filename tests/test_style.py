import pytest

from figkit import Box, Figure, Style, Text, Theme, use_theme
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


def test_classes_are_resolved_lazily_against_the_live_theme():
    # the class does not exist when the element is built, only later
    b = Box("x", classes="brandy", add=False)
    assert b.prop("fill") != "#ff00ff"
    b.theme = DEFAULT_THEME.derive(styles={"brandy": Style(fill="#ff00ff")})
    assert b.prop("fill") == "#ff00ff"


def test_multiple_classes_later_wins():
    b = Box("x", style="block blue", add=False)
    assert b.classes == ("block", "blue")
    assert b.prop("fill") == DEFAULT_THEME.styles["blue"]["fill"]
    b.add_class("green")
    assert b.prop("fill") == DEFAULT_THEME.styles["green"]["fill"]
    b.remove_class("green")
    assert b.prop("fill") == DEFAULT_THEME.styles["blue"]["fill"]


def test_kwargs_beat_classes():
    assert Box("x", style="blue", fill="#010203", add=False).prop("fill") == "#010203"


def test_dotted_class_keys_are_accepted():
    t = DEFAULT_THEME.derive(styles={".accent": Style(fill="#abcabc")})
    assert Box("x", classes=".accent", theme=t, add=False).prop("fill") == "#abcabc"


def test_unknown_class_warns_at_render():
    from figkit import Figure
    with Figure() as fig:
        Box("x", classes="nope")
    with pytest.warns(UserWarning, match="unknown style class"):
        fig.to_svg()


def test_class_names_reach_the_svg():
    from figkit import Figure
    with Figure() as fig:
        Box("x", classes="blue emphasis")
    assert 'class="blue emphasis"' in fig.to_svg(pretty=False)


# -- unknown properties -----------------------------------------------------

def test_a_misspelled_property_is_refused_not_ignored():
    """The whole class of bug: a name figkit does not read used to be stored
    and never looked at, so the figure silently rendered the default."""
    from figkit.style import UnknownProperty

    with pytest.raises(UnknownProperty):
        Text("hi", add=False, sizee=8)
    with pytest.raises(UnknownProperty):
        Box("hi", add=False, colour="red")
    with pytest.raises(UnknownProperty):
        Style(wibble=1)


def test_the_refusal_suggests_the_name_you_meant():
    from figkit.style import UnknownProperty

    with pytest.raises(UnknownProperty, match="stroke_width"):
        Box("hi", add=False, strokewidth=2)


def test_components_can_declare_properties_of_their_own():
    from figkit.style import PROPS, UnknownProperty, register_props

    with pytest.raises(UnknownProperty):
        Style(wave_amplitude=3)
    try:
        register_props("wave_amplitude")
        assert Style(wave_amplitude=3)["wave_amplitude"] == 3
    finally:
        PROPS.discard("wave_amplitude")


def test_size_means_font_size_like_it_does_in_measure_text():
    """measure_text takes size=; Text taking only font_size meant measuring at
    one size and rendering at another."""
    from figkit.fonts import measure_text

    assert Text("hi", add=False, size=8).bbox == Text("hi", add=False,
                                                      font_size=8).bbox
    assert Text("Hello", add=False, size=7.5).bbox.w == pytest.approx(
        measure_text("Hello", size=7.5), abs=0.01)


def test_fill_on_text_means_its_colour():
    """Text has no fill of its own, so dropping it renders the default."""
    t = Text("hi", add=False, fill="#ff0000")
    assert t.text_color() == "#ff0000"
    # An explicit colour still wins.
    assert Text("hi", add=False, fill="#ff0000", color="#00ff00") \
        .text_color() == "#00ff00"
