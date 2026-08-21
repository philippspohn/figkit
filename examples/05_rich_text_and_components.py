"""Rich text spans, reusable components, and formula-style layout.

Shows: `Span` for per-word colour/strike/underline, a `Component` that
publishes its own anchors, `LabelledMatrix` for matrix expressions,
`hstack(align="baseline")` for setting them like an equation, plus
`self_loop` and `brace_around`.

Run:  python examples/05_rich_text_and_components.py
Out:  out/05_rich_text_and_components.{svg,png}
"""

import random

from figkit import *

rng = random.Random(3)


class Stage(Component):
    """A pipeline stage with a named input and output port.

    Because the ports are exposed, callers write `arrow(a.out, b.inp)` instead
    of reaching into `stage.children[2]`.
    """

    def build(self, title, subtitle=None, w=150):
        label = title if subtitle is None else [title, Span(f"\n{subtitle}",
                                                            size=11,
                                                            color="@muted")]
        body = Box(label, w=w, style="block", padding=(10, 12))
        inp = Dot(body.w, r=4.5, fill="@primary")
        out = Dot(body.e, r=4.5, fill="@accent")
        self.expose("body", body)
        self.expose("inp", inp.center)
        self.expose("out", out.center)
        return [body, inp, out]


with Figure(pad=26, background="#ffffff") as fig:

    # ---- 1. rich text --------------------------------------------------
    Text([Span("Rich text", bold=True), " — one line, several styles"],
         font_size=16, align="left").at(0, 0)
    Text(["accuracy ", Span("76.1", strike=True, color="@muted"), " → ",
          Span("94.6", color="@good", bold=True), " after ",
          Span("pretraining", italic=True), ", measured on ",
          Span("held-out data", underline=True)],
         font_size=14, align="left").at(0, 30)

    # ---- 2. a matrix expression, set like an equation -------------------
    lhs = Text("$\\Pi_{\\mathcal{NM}} \;=\;$", font_size=19)
    left = LabelledMatrix([[rng.random() for _ in range(4)] for _ in range(5)],
                          cell=17, cmap="grays", stroke="#ffffff",
                          row_label="seq len", col_label="$d$",
                          brackets="round")
    times = Text("$\\times$", font_size=19)
    right = LabelledMatrix([[rng.random() for _ in range(3)] for _ in range(4)],
                           cell=17, cmap="blues", stroke="#ffffff",
                           col_label="$d$", brackets="square")
    formula = hstack([lhs, left, times, right], gap=16, align="baseline")
    formula.below_of(fig.children[1], gap=54).align_to(fig.children[0], "left")

    # ---- 3. components with named ports ---------------------------------
    encode = Stage("Encode", "tokens → $z$").below_of(formula, gap=90)
    encode.align_to(fig.children[0], "left")
    solve = Stage("Solve", "argmin $E$").right_of(encode, gap=72)
    decode = Stage("Decode", "$z$ → labels").right_of(solve, gap=72)

    arrow(encode.out, solve.inp, label="$z$")
    arrow(solve.out, decode.inp, label="$C$")
    self_loop(solve.body, side="top", size=34, label="refine", head_size=8)

    brace_around([encode, decode], side="bottom", gap=34, depth=12,
                 label="trained end to end")

print(fig.audit())
fig.save("out/05_rich_text_and_components.svg")
# PNG needs a rasteriser (cairosvg, rsvg-convert, resvg, …); the SVG
# above is always written, so skip quietly when none is installed.
if any(available_backends().values()):
    fig.save("out/05_rich_text_and_components.png", scale=2)
print(fig)
