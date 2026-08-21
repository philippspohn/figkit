"""A two-panel explainer figure in the style of an interpretability blog post.

Shows: two side-by-side panels, programmatic node grids, curved edges whose
opacity and width come from data, and a shared caption block.

Run:  python examples/02_attribution.py   ->  out/02_attribution.{svg,png}
"""

import random

from figkit import *

INK = "#2b2724"
ORANGE = "#c2600c"
PLUM = "#6b3b47"
PAPER_BG = "#faf9f7"

T = SOFT.derive(
    font_family="Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif",
    font_size=13,
    color=INK,
    palette={"ink": INK, "orange": ORANGE, "plum": PLUM, "faint": "#d9d5d0"},
    box=Style(fill="#ffffff", stroke="#c9c4bd", stroke_width=1.2, radius=6,
              padding=(7, 9), shadow=None),
    arrow=Style(stroke=INK, stroke_width=1.4, head_size=8),
    label=Style(font_size=12, color="#6a635c"),
)

rng = random.Random(4)


def panel_heading(title, subtitle, width):
    """Bold title + wrapped grey subtitle, returned as one movable group."""
    head = Text(title, bold=True, font_size=15, align="left", wrap=width)
    sub = Text(subtitle, font_size=13, align="left", wrap=width,
               color="#5f584f", line_height=1.35)
    sub.below_of(head, gap=7).align_to(head, "left")
    return Group(head, sub)


with Figure(theme=T, pad=28, background=PAPER_BG) as fig:

    # ======================================================================
    # LEFT PANEL — replacement model
    # ======================================================================
    left_head = panel_heading(
        "Replacement Model",
        "Replaces transformer model neurons with more interpretable features.",
        330).at(0, 0)

    LAYERS = 3
    lane_h = 108
    top = left_head.bbox.y1 + 62

    residual_x = 26
    neuron_boxes, feature_boxes, plus_nodes, layer_labels = [], [], [], []

    for i in range(LAYERS):
        y = top + (LAYERS - 1 - i) * lane_h

        lbl = Text(f"Layer {i + 1}", font_size=12, align="right",
                   color="#5f584f").at(residual_x - 16, y + 22, anchor="e")
        layer_labels.append(lbl)

        # dashed lane rule
        Line((residual_x - 10, y + 22), (residual_x + 320, y + 22), stroke="#cfcac3",
             stroke_width=1, stroke_dash="dotted", z=-20)

        # the "neuron" block: four little squares in a rounded container
        cells = [Box(None, 0, 0, 13, 13, fill="#efece7", stroke="#b9b2a8",
                     stroke_width=1, radius=2) for _ in range(4)]
        row = hstack(cells, gap=4)
        neurons = fit(row, pad=8, fill="#e6e2dc", stroke="#c9c4bd", radius=6)
        neurons.at(residual_x + 22, y)
        neuron_boxes.append(neurons)

        # the "feature" block: six circles in an orange-tinted container
        dots = [Circle(None, r=6.5, fill="#ffffff", stroke="#d9b48f",
                       stroke_width=1.2) for _ in range(6)]
        drow = hstack(dots, gap=5)
        feats = fit(drow, pad=9, fill="#fdf0e2", stroke="#e8b887", radius=8)
        feats.right_of(neurons, gap=110).align_to(neurons, "center_y")
        feature_boxes.append(feats)

        # residual-stream junction
        plus = Circle("+", r=10, fill="#f0ede8", stroke="#b9b2a8",
                      font_size=12, color="#4a443d")
        plus.at(residual_x, neurons.bbox.y0 - 12, anchor="center")
        plus_nodes.append(plus)

    # residual stream spine + its arrowhead
    spine_bottom = plus_nodes[0].bbox.y1 + 46
    spine_top = plus_nodes[-1].bbox.y0 - 20
    # The spine deliberately runs behind the junction nodes, so opt it out of
    # the crossing check rather than have fig.audit() report it every run.
    arrow((residual_x, spine_bottom), (residual_x, spine_top),
          stroke="#b9b2a8", stroke_width=1.6, head_size=9).ignore_audit()
    Text("Residual\nstream", font_size=12, color="#5f584f",
         align="center").at(residual_x, spine_bottom + 10, anchor="n")

    # neurons read from / write to the residual stream
    for plus, neurons in zip(plus_nodes, neuron_boxes):
        curve((residual_x, neurons.bbox.cy + 26), neurons.s,
              stroke="#b9b2a8", stroke_width=1.3, head="none", bend=0.0)
        curve(neurons.n, plus.s, stroke="#b9b2a8", stroke_width=1.3,
              head="none")

    # features read from every earlier layer (the orange fan)
    for i, feats in enumerate(feature_boxes):
        curve(plus_nodes[i].e, feats.w, stroke=ORANGE, stroke_width=1.5,
              head="triangle", head_size=7, bend=0.0)
        for j in range(i + 1, LAYERS):
            curve(feats.n, plus_nodes[j].e, stroke=ORANGE, stroke_width=1.4,
                  head="none", bend=0.12)
        # highlight the junction itself rather than stacking a dot on the "+"
        plus_nodes[i].restyle(fill=ORANGE, stroke=ORANGE, color="#ffffff")

    Text("Neuron", font_size=12, color="#5f584f").below_of(
        neuron_boxes[0], gap=28).align_to(neuron_boxes[0], "center_x")
    arrow(Point(neuron_boxes[0].bbox.cx, neuron_boxes[0].bbox.y1 + 26),
          neuron_boxes[0].s + (0, 2), stroke="#8a837a", stroke_width=1,
          head_size=6)

    Text("Feature", font_size=12, color="#5f584f").below_of(
        feature_boxes[0], gap=28).align_to(feature_boxes[0], "center_x")
    arrow(Point(feature_boxes[0].bbox.cx, feature_boxes[0].bbox.y1 + 26),
          feature_boxes[0].s + (0, 2), stroke="#8a837a", stroke_width=1,
          head_size=6)

    left = group(left_head, *layer_labels, *neuron_boxes, *feature_boxes,
                 *plus_nodes)

    # ======================================================================
    # RIGHT PANEL — attribution graph
    # ======================================================================
    right_head = panel_heading(
        "Attribution Graph",
        "Depicts influence of features on one another, allowing us to trace "
        "intermediate steps the model uses to produce its output.", 430)
    right_head.right_of(left, gap=96).align_to(left_head, "top")

    ROWS = ["Embeddings", "Layer 1", "Layer 2", "Layer 3"]
    TOKENS = ["Token 1", "Token 2", "Token 3", "Token 4"]
    row_gap, col_gap, dot_gap = 104, 116, 17

    grid_left = right_head.bbox.x0 + 26
    output_y = right_head.bbox.y1 + 30
    grid_bottom = output_y + 74 + (len(ROWS) - 1) * row_gap

    nodes = {}          # (row, col, k) -> Dot
    for r, _row_name in enumerate(ROWS):
        y = grid_bottom - r * row_gap
        for c in range(len(TOKENS)):
            k_count = 1 if r == 0 else rng.randint(2, 3)
            base_x = grid_left + c * col_gap
            for k in range(k_count):
                nodes[(r, c, k)] = Dot((base_x + k * dot_gap, y), r=5.5,
                                       fill="#e7e3de", stroke="none")

    # row labels on the right, token labels underneath
    for r, name in enumerate(ROWS):
        Text(name, font_size=12, color="#5f584f", align="left").at(
            grid_left + (len(TOKENS) - 1) * col_gap + 92,
            grid_bottom - r * row_gap, anchor="w")
        Line((grid_left - 14, grid_bottom - r * row_gap),
             (grid_left + (len(TOKENS) - 1) * col_gap + 84,
              grid_bottom - r * row_gap),
             stroke="#d9d5d0", stroke_width=1, stroke_dash="dotted", z=-20)
    for c, name in enumerate(TOKENS):
        Text(name, font_size=12, color="#4a443d").at(
            grid_left + c * col_gap + dot_gap / 2, grid_bottom + 30,
            anchor="n")

    output = Dot((grid_left + (len(TOKENS) - 1) * col_gap + dot_gap,
                  output_y), r=7, fill=PLUM)
    Text("output", font_size=12, color="#4a443d").right_of(output, gap=12)

    # ---- edges: weight drives both opacity and stroke width --------------
    keys = sorted(nodes)
    edges = []
    for (r, c, k) in keys:
        if r >= len(ROWS) - 1:
            continue
        for _ in range(rng.randint(1, 3)):
            tr = rng.choice([r + 1, min(r + 2, len(ROWS) - 1)])
            tc = rng.choice([c, min(c + 1, len(TOKENS) - 1)])
            cands = [k2 for (r2, c2, k2) in keys if r2 == tr and c2 == tc]
            if not cands:
                continue
            edges.append(((r, c, k), (tr, tc, rng.choice(cands)),
                          rng.random() ** 2))

    strong = set()
    for src, dst, wgt in edges:
        curve(nodes[src].n, nodes[dst].s, stroke=PLUM,
              stroke_width=0.35 + 2.1 * wgt, opacity=0.10 + 0.75 * wgt,
              head="none", bend=0.0)
        if wgt > 0.55:
            strong.add(src)
            strong.add(dst)

    for key in strong:
        nodes[key].restyle(fill=PLUM).to_front()

    # the traced path into the output node
    for c in (0, 2, 3):
        top_key = max((k for k in keys if k[0] == len(ROWS) - 1 and k[1] == c),
                      default=None)
        if top_key:
            nodes[top_key].restyle(fill=PLUM).to_front()
            curve(nodes[top_key].n, output.s if c != 3 else output.w,
                  stroke=PLUM, stroke_width=1.8, opacity=0.85, head="none")

fig.save("out/02_attribution.svg")
fig.save("out/02_attribution.png", scale=2)
print(fig, "-> out/02_attribution.svg")
