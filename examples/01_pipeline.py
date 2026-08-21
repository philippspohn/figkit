"""A shape-matching pipeline figure, in the style of an ML paper.

Shows: themes, relative placement, live anchors, inline LaTeX, matrices,
elbow routing and custom vector graphics.

Run:  python examples/01_pipeline.py     ->  out/01_pipeline.{svg,png}
"""

import math
import random

from figkit import *

# --------------------------------------------------------------------------
# 1. Theme — change the look of the whole figure from one place
# --------------------------------------------------------------------------
T = PAPER.derive(
    font_size=13,
    palette={
        "solver": "#bfdcf2", "solver_edge": "#5b8db8",
        "pointmap": "#b9c7d6", "pointmap_edge": "#63788e",
        "loss": "#c9e6cd", "loss_edge": "#5f9c6c",
    },
    box=Style(stroke_width=1.3, padding=(9, 13)),
    arrow=Style(stroke="#1b1b1b", stroke_width=1.25, head_size=8),
    styles={
        "solver": Style(fill="@solver", stroke="@solver_edge", radius=3),
        "pointmap": Style(fill="@pointmap", stroke="@pointmap_edge", radius=3),
        "loss": Style(fill="@loss", stroke="@loss_edge", radius=3),
        "extractor": Style(fill="#efefef", stroke="#1b1b1b", radius=2),
    },
)


# --------------------------------------------------------------------------
# 2. Custom graphics — just build them out of figkit primitives
# --------------------------------------------------------------------------
def mesh_blob(seed, w=112, h=92):
    """Stand-in for a 3D mesh render: a wireframed organic blob."""
    rng = random.Random(seed)
    n = 14
    pts = [Point(w / 2 + math.cos(2 * math.pi * i / n) * (0.42 + 0.08 * rng.random()) * w,
                 h / 2 + math.sin(2 * math.pi * i / n) * (0.42 + 0.08 * rng.random()) * h)
           for i in range(n)]
    body = Polygon(pts, fill="#dcdcdc", stroke="#a6a6a6", stroke_width=1.0,
                   stroke_linejoin="round", add=False)
    wires = [Line(pts[i], pts[(i + 4) % n], stroke="#c6c6c6", stroke_width=0.6,
                  add=False) for i in range(n)]
    return Group(body, *wires)


def colored_mesh(seed, w=112, h=92):
    """The same blob, coloured per region — the 'correspondence' output."""
    rng = random.Random(seed)
    n = 14
    pts = [Point(w / 2 + math.cos(2 * math.pi * i / n) * (0.42 + 0.08 * rng.random()) * w,
                 h / 2 + math.sin(2 * math.pi * i / n) * (0.42 + 0.08 * rng.random()) * h)
           for i in range(n)]
    centre = Point(w / 2, h / 2)
    wedges = [Polygon([centre, pts[i], pts[(i + 1) % n]],
                      fill=colormap("spectral", (i / n + 0.15 * rng.random()) % 1.0),
                      fill_opacity=0.9, stroke="#ffffff", stroke_width=0.8,
                      add=False) for i in range(n)]
    return Group(*wedges)


# --------------------------------------------------------------------------
# 3. The figure
# --------------------------------------------------------------------------
rng = random.Random(7)
rand4 = lambda: [[rng.random() for _ in range(4)] for _ in range(4)]

with Figure(theme=T, pad=26, background="#ffffff") as fig:

    # ---- column 1: inputs ------------------------------------------------
    mesh_m = mesh_blob(3).at(0, 0)
    mesh_n = mesh_blob(11).below_of(mesh_m, gap=70)
    # lifted clear of the arrows that leave each mesh (fig.audit() flags a clip)
    Text("$\\mathcal{M}$", font_size=16).right_of(mesh_m, gap=4, dy=-16)
    Text("$\\mathcal{N}$", font_size=16).right_of(mesh_n, gap=4, dy=-16)

    TOP = mesh_m.bbox.cy          # the two horizontal "lanes" of the figure
    BOT = mesh_n.bbox.cy
    MID = (TOP + BOT) / 2

    # ---- column 2: shared feature extractor ------------------------------
    extractor = Box("Feature\nExtractor", style="extractor", w=112, bold=True,
                    valign="top", padding=(12, 12))
    extractor.right_of(group(mesh_m, mesh_n), gap=58).center_at(None, MID)
    extractor.resize(h=bbox_of([mesh_m, mesh_n]).h + 24, anchor="center")

    theta = Box("$\\Theta$", style="extractor", w=72, fill="#f8f8f8",
                font_size=15)
    theta.resize(h=extractor.height - 58).inside(extractor, anchor="s", pad=12)

    # ---- column 3: feature vectors ---------------------------------------
    f_m = Vector([0.9, 0.3, 0.62, 0.12, 0.05, 0.45], cell=(48, 12),
                 cmap="grays", stroke="#333333", stroke_width=0.7)
    f_m.right_of(extractor, gap=34).center_at(None, TOP)
    f_n = Vector([0.35, 0.68, 0.18, 0.92, 0.5, 0.02], cell=(48, 12),
                 cmap="grays", stroke="#333333", stroke_width=0.7)
    f_n.right_of(extractor, gap=34).center_at(None, BOT)
    Text("$F_{\\mathcal{M}}$", font_size=15).below_of(f_m, gap=6)
    Text("$F_{\\mathcal{N}}$", font_size=15).below_of(f_n, gap=6)

    # ---- column 4: the two computation blocks ----------------------------
    solver = Box("**FMap Solver**\n\n"
                 "$E_{\\mathrm{data}} + \\lambda E_{\\mathrm{reg}}$",
                 style="solver", w=200, h=112, markup=True)
    solver.right_of(f_m, gap=62).center_at(None, TOP)

    pointmap = Box("**PointMap Computation**\n\n"
                   "$\\Pi_{\\mathcal{NM}} = \\mathrm{Softmax}"
                   "(\\langle F_{\\mathcal{N}}, F_{\\mathcal{M}}\\rangle/\\tau)$",
                   style="pointmap", w=270, h=112, markup=True)
    pointmap.right_of(f_n, gap=62).center_at(None, BOT)

    # ---- column 5: the matrices they produce -----------------------------
    c_mn = Matrix(rand4(), cell=15, cmap="viridis")
    c_mn.right_of(solver, gap=40).center_at(None, TOP)
    Text("$C_{\\mathcal{MN}}$", font_size=14).below_of(c_mn, gap=9)

    pi_nm = Matrix(rand4(), cell=15, cmap="grays")
    pi_nm.right_of(pointmap, gap=40).center_at(None, BOT)
    Text("$\\Pi_{\\mathcal{NM}}$", font_size=14).below_of(pi_nm, gap=9)

    # ---- column 6: losses (top lane) and the fused map (bottom lane) -----
    l_couple = Box("$L_{\\mathrm{couple}}$", style="loss", w=132, h=42)
    l_fmap = Box("$L_{\\mathrm{fmap}}$", style="loss", w=132, h=42)
    losses = vstack([l_couple, l_fmap], gap=20, align="center")
    losses.right_of(c_mn, gap=52).center_at(None, TOP)

    fuse = Box("$C^{\\Pi}_{\\mathcal{MN}} = \\phi^{\\dagger}_{\\mathcal{N}}"
               "\\Pi_{\\mathcal{NM}}\\phi_{\\mathcal{M}}$",
               style="solver", w=210, h=48)
    fuse.right_of(pi_nm, gap=52).center_at(None, BOT)

    c_pi = Matrix(rand4(), cell=15, cmap="viridis")
    c_pi.above_of(fuse, gap=54).right_of(losses, gap=34)
    Text("$C^{\\Pi}_{\\mathcal{MN}}$", font_size=14).above_of(c_pi, gap=7)

    # ---- column 7: outputs ------------------------------------------------
    out_m = colored_mesh(3).right_of(c_pi, gap=78).center_at(None, TOP)
    out_n = colored_mesh(11).right_of(fuse, gap=96).center_at(None, BOT)

    # ---- wiring: anchors are live, so this all stays glued together ------
    arrow(mesh_m.e + (20, 0), extractor.w)
    arrow(mesh_n.e + (20, 0), extractor.w)
    arrow(extractor.e, f_m.w)
    arrow(extractor.e, f_n.w)

    for src in (f_m, f_n):
        elbow(src.e, solver.w, stub=16)
        elbow(src.e, pointmap.w, stub=16)

    arrow(solver.e, c_mn.w)
    arrow(pointmap.e, pi_nm.w)
    elbow(c_mn.e, l_couple.w, stub=14)
    elbow(c_mn.e, l_fmap.w, stub=14)
    arrow(pi_nm.e, fuse.w)
    arrow(fuse.n, c_pi.s)
    elbow(c_pi.nw, l_couple.e, stub=20, corner=8)

    arrow(fuse.e, out_n.w)
    elbow(c_pi.e, out_m.w, stub=18, corner=8)

fig.save("out/01_pipeline.svg")
fig.save("out/01_pipeline.png", scale=2)
print(fig, "-> out/01_pipeline.svg")
