"""Data-driven graphics: a coordinate Frame, a legend, a table and a brace.

Shows that "plots" are just figures with a coordinate mapping — every mark is
an ordinary figkit element you can anchor to and annotate.

Run:  python examples/03_data_and_plots.py  ->  out/03_data_and_plots.{svg,png}
"""

import math
import random

from figkit import *

rng = random.Random(0)
xs = list(range(0, 51))
runs = {
    "baseline": [0.42 + 0.34 * (1 - math.exp(-x / 13)) + rng.gauss(0, 0.012)
                 for x in xs],
    "+ pretraining": [0.55 + 0.33 * (1 - math.exp(-x / 9)) + rng.gauss(0, 0.010)
                      for x in xs],
    "ours": [0.61 + 0.34 * (1 - math.exp(-x / 6)) + rng.gauss(0, 0.008)
             for x in xs],
}
COLORS = dict(zip(runs, palette("figkit", 3)))

with Figure(pad=26, background="#ffffff") as fig:

    Text("Validation accuracy over training", bold=True, font_size=17,
         align="left").at(0, 0)

    # ---- the plot ---------------------------------------------------------
    fr = Frame(w=430, h=240, xlim=(0, 50), ylim=(0.35, 1.0))
    fr.at(46, 52)
    fr.gridlines(n=6)
    fr.xaxis(n=6, title="epoch")
    fr.yaxis(n=5, title="accuracy", fmt=lambda v: f"{v:.0%}")

    # a shaded "warm-up" region with its own label, in data coordinates
    fr.region(0, 8, 0.35, 1.0, fill="#4C72B0", fill_opacity=0.09)
    fr.text("warm-up", 4, 0.965, font_size=11, color="#6b7280")

    for name, ys in runs.items():
        fr.line(xs, ys, stroke=COLORS[name], stroke_width=2.2)
        fr.scatter(xs[::10], ys[::10], size=6, fill=COLORS[name],
                   stroke="#ffffff", stroke_width=1.2)

    # annotate a specific data point — anchors work in data space too
    peak = Dot(fr.pt(50, runs["ours"][-1]), r=5, fill=COLORS["ours"])
    note = Box("best: {:.1%}".format(runs["ours"][-1]), style="card",
               font_size=11, padding=(5, 8))
    note.above_of(peak, gap=30).left_of(peak, gap=8)
    arrow(note.se, peak.nw, stroke="#9aa1ac", head_size=6, stroke_width=1)

    legend = Legend([(n, COLORS[n], {"marker": "line"}) for n in runs],
                    font_size=12)
    legend.inside(fr.plot_area, anchor="se", pad=14)

    # ---- a results table beside it ---------------------------------------
    table = Table(
        [["variant", "acc", "params"],
         ["baseline", "76.1", "22M"],
         ["+ pretraining", "88.0", "22M"],
         ["ours", "94.6", "24M"]],
        header=True, align=["left", "right", "right"], stripe=True)
    table.right_of(fr, gap=76).align_to(fr.plot_area, "top")

    Text("Table 1: final metrics", font_size=11, color="#6b7280",
         align="left").below_of(table, gap=8).align_to(table, "left")

    # a brace grouping the two strong variants
    Brace(table.cell(2, 2).ne, table.cell(3, 2).se, depth=10, side="right",
          label="+18.5 pts", label_style=Style(font_size=11, color="@good"),
          stroke="@good").right_of(table, gap=6, align="center") \
        .align_to(bbox_of([table.cell(2, 0), table.cell(3, 0)]), "center_y")

    # ---- a colour-coded confusion-ish matrix -----------------------------
    m = Matrix([[0.92, 0.05, 0.03], [0.04, 0.89, 0.07], [0.02, 0.11, 0.87]],
               cell=44, cmap="blues", show_values=True, value_fmt="{:.2f}",
               stroke="#ffffff", stroke_width=2)
    m.below_of(table, gap=64).align_to(table, "left")
    Text("confusion", font_size=11, color="#6b7280").above_of(m, gap=8) \
        .align_to(m, "left")
    ColorBar("blues", 0, 1, w=10, h=m.height, labels=True) \
        .right_of(m, gap=14).align_to(m, "center_y")

fig.save("out/03_data_and_plots.svg")
fig.save("out/03_data_and_plots.png", scale=2)
print(fig)
