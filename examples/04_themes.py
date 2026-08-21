"""The same diagram drawn in every built-in theme.

Not one colour is set on an element below — the theme cascade decides fills,
strokes, fonts, corner radii and arrow heads.  Swap `get_theme(name)` for your
own `Theme(...)` to restyle a whole figure at once.

Run:  python examples/04_themes.py   ->  out/04_themes.{svg,png}
"""

from figkit import *

THEME_ORDER = ["default", "paper", "slide", "soft", "minimal", "blueprint",
               "dark"]
BACKDROP = {"dark": "#141821", "blueprint": "#0b2447"}
CARD_W = 430


def diagram(theme, name):
    """One little pipeline, styled entirely by the theme."""
    with use_theme(theme):
        enc = Box("Encoder", style="block", w=98)
        lat = Box("$z$", style="blue", w=52)
        dec = Box("Decoder", style="green", w=98)
        row = hstack([enc, lat, dec], gap=30, align="center").at(0, 0)

        wires = [arrow(enc.e, lat.w), arrow(lat.e, dec.w),
                 curve(dec.s, enc.s, bend=0.42, label="loss",
                       stroke_dash="dashed", label_side="below")]

        chip = Pill("v2", padding=(3, 9), font_size=11, style="warm")
        chip.right_of(dec, gap=14).align_to(dec, "center_y")

        body = fit(row, chip, *wires, pad=18, label="autoencoder",
                   label_pos="below")
        title = Text(name, bold=True, font_size=15, align="left")
        title.above_of(body, gap=14).align_to(body, "left")

        card = Group(title, body)
        pad_r = max(0.0, CARD_W - card.bbox.w - 44)
        bg = Panel([card, Spacer(pad_r, 1).right_of(card, gap=0)],
                   pad=22, fill=BACKDROP.get(name, "#ffffff"), stroke="none",
                   radius=14, z=-5000, add=False)
        return Group(bg, card, theme=theme)


with Figure(pad=22, background="#eef0f3") as fig:
    grid([diagram(get_theme(n), n) for n in THEME_ORDER],
         cols=2, gap=(24, 24), align="nw")

fig.save("out/04_themes.svg")
fig.save("out/04_themes.png", scale=2)
print(fig)
