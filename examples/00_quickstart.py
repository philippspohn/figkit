"""The 20-line version: boxes, arrows, a label, an export."""

from figkit import *

with Figure(pad=24) as fig:
    data = Box("Dataset", style="block", w=110)
    model = Box("Model\n$f_\\theta$", style="blue", w=110).right_of(data, gap=70)
    loss = Box("Loss $\\mathcal{L}$", style="green", w=110).right_of(model, gap=70)

    arrow(data.e, model.w, label="$x$")
    arrow(model.e, loss.w, label="$\\hat{y}$")
    curve(loss.s, model.s, bend=0.35, label="gradients", label_side="below",
          stroke="@accent", stroke_dash="dashed")

    Text("A very small training loop", bold=True, font_size=16) \
        .above_of(group(data, model, loss), gap=26)

fig.save("out/00_quickstart.svg")
# PNG needs a rasteriser (cairosvg, rsvg-convert, resvg, …); the SVG
# above is always written, so skip quietly when none is installed.
if any(available_backends().values()):
    fig.save("out/00_quickstart.png", scale=2)
print(fig)
