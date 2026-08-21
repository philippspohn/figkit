import pytest

from figkit.colors import (colormap, contrast_color, darken, lighten, mix,
                           normalize, palette, parse_color, to_hex)


@pytest.mark.parametrize("spec,expected", [
    ("#f0a", (255, 0, 170, 1.0)),
    ("#ff00aa", (255, 0, 170, 1.0)),
    ("#ff00aa80", (255, 0, 170, 128 / 255)),
    ("rgb(1, 2, 3)", (1, 2, 3, 1.0)),
    ("rgba(1,2,3,0.5)", (1, 2, 3, 0.5)),
    ("white", (255, 255, 255, 1.0)),
    ((10, 20, 30), (10, 20, 30, 1.0)),
])
def test_parse_color(spec, expected):
    got = parse_color(spec)
    assert got[:3] == expected[:3]
    assert got[3] == pytest.approx(expected[3], abs=1e-3)


def test_parse_color_none_and_errors():
    assert parse_color(None) is None
    assert parse_color("none") is None
    with pytest.raises(ValueError):
        parse_color("not-a-color")


def test_mix_lighten_darken():
    assert to_hex(mix("#000000", "#ffffff", 0.5)) == "#808080"
    assert to_hex(lighten("#000000", 1.0)) == "#ffffff"
    assert to_hex(darken("#ffffff", 1.0)) == "#000000"


def test_contrast_color():
    assert contrast_color("#ffffff") == "#111111"
    assert contrast_color("#000000") == "#ffffff"


def test_colormap_endpoints_and_reverse():
    assert to_hex(colormap("viridis", 0.0)) == "#440154"
    assert to_hex(colormap("viridis", 1.0)) == "#fde725"
    assert to_hex(colormap("viridis_r", 0.0)) == "#fde725"
    assert to_hex(colormap(["#000000", "#ffffff"], 0.5)) == "#808080"
    with pytest.raises(KeyError):
        colormap("nope", 0.5)


def test_palette_and_normalize():
    assert len(palette("figkit", 15)) == 15
    assert normalize([0, 5, 10]) == [0.0, 0.5, 1.0]
    assert normalize([3, 3, 3]) == [0.5, 0.5, 0.5]
