"""Ready-made themes. Start from one and ``.derive(...)`` your own."""

from __future__ import annotations

from .style import DEFAULT_THEME, MONO, SERIF, Style, Theme

__all__ = ["PAPER", "SLIDE", "DARK", "BLUEPRINT", "MINIMAL", "SOFT", "THEMES",
           "get_theme"]

#: Muted, serif-labelled look for LaTeX papers.
PAPER = DEFAULT_THEME.derive(
    name="paper",
    font_family=SERIF,
    font_size=12,
    color="#111111",
    stroke_width=1.1,
    radius=3,
    palette={
        "text": "#111111", "muted": "#555555", "line": "#222222",
        "surface": "#ffffff", "surface_alt": "#f0f0f0",
        "primary": "#3B6EA5", "primary_soft": "#cfe0f2",
        "accent": "#B5622A", "accent_soft": "#f2dcc9",
        "good": "#3E7C4B", "good_soft": "#d6e8da", "bad": "#A93B3B",
    },
    box=Style(fill="#ffffff", stroke="#222222", stroke_width=1.1,
              padding=(6, 10), radius=3),
    arrow=Style(stroke="#222222", stroke_width=1.1, head_size=7),
    panel=Style(stroke="#888888", stroke_width=0.9, radius=4),
    label=Style(font_size=10.5, color="#333333"),
    styles={
        "block": Style(fill="#f2f2f2", stroke="#111111", stroke_width=1.2),
        "blue": Style(fill="#cfe0f2", stroke="#3B6EA5"),
        "green": Style(fill="#d6e8da", stroke="#3E7C4B"),
        "warm": Style(fill="#f2dcc9", stroke="#B5622A"),
        "ghost": Style(fill="none", stroke="#888888", stroke_dash="dashed"),
    },
)

#: Bigger type and chunkier strokes, for slides and posters.
SLIDE = DEFAULT_THEME.derive(
    name="slide",
    font_size=19,
    stroke_width=2.2,
    radius=10,
    box=Style(padding=(12, 18), stroke_width=2.2, radius=10),
    arrow=Style(stroke_width=2.4, head_size=12),
    label=Style(font_size=15),
)

#: Light-on-dark, for dark-mode blog posts.
DARK = DEFAULT_THEME.derive(
    name="dark",
    color="#e8eaed",
    stroke_width=1.5,
    palette={
        "text": "#e8eaed", "muted": "#9aa4b2", "line": "#8b95a5",
        "surface": "#1b1f27", "surface_alt": "#252b36",
        "primary": "#7aa2f7", "primary_soft": "#26344f",
        "accent": "#e0af68", "accent_soft": "#3d3222",
        "good": "#9ece6a", "good_soft": "#2b3a25", "bad": "#f7768e",
    },
    box=Style(fill="#252b36", stroke="#8b95a5", color="#e8eaed"),
    text=Style(color="#e8eaed"),
    label=Style(color="#c3cad6"),
    arrow=Style(stroke="#aab4c4"),
    panel=Style(stroke="#4a5364", fill="none"),
    matrix=Style(stroke="#1b1f27"),
    axis=Style(stroke="#9aa4b2"),
    grid=Style(stroke="#333a47"),
    styles={
        "block": Style(fill="#2c3340", stroke="#aab4c4"),
        "blue": Style(fill="#26344f", stroke="#7aa2f7"),
        "green": Style(fill="#2b3a25", stroke="#9ece6a"),
        "warm": Style(fill="#3d3222", stroke="#e0af68"),
        "ghost": Style(fill="none", stroke="#5c6675", stroke_dash="dashed"),
        "card": Style(fill="#222834", stroke="#39414f", radius=12),
    },
)

#: Technical-drawing look: thin monochrome lines on a tinted ground.
BLUEPRINT = DEFAULT_THEME.derive(
    name="blueprint",
    font_family=MONO,
    font_size=12,
    color="#dbeafe",
    stroke_width=1.0,
    radius=0,
    palette={"text": "#dbeafe", "line": "#93c5fd", "surface": "#0f2f5c",
             "primary": "#93c5fd", "muted": "#7ea6d8"},
    box=Style(fill="none", stroke="#93c5fd", color="#dbeafe", radius=0),
    arrow=Style(stroke="#93c5fd", head="open", head_size=8),
    panel=Style(stroke="#5b8fc7", stroke_dash="dashed"),
    text=Style(color="#dbeafe"),
    label=Style(color="#bfdbfe", font_size=10),
    styles={
        "block": Style(fill="none", stroke="#93c5fd", stroke_width=1.4),
        "blue": Style(fill="#173f70", stroke="#93c5fd"),
        "green": Style(fill="#134e4a", stroke="#5eead4"),
        "warm": Style(fill="#4a3417", stroke="#fbbf24"),
        "ghost": Style(fill="none", stroke="#5b8fc7", stroke_dash="dashed"),
        "plain": Style(fill="none", stroke="none"),
        "card": Style(fill="none", stroke="#5b8fc7", radius=0),
    },
)

#: No fills, no rounding — just hairlines and text.
MINIMAL = DEFAULT_THEME.derive(
    name="minimal",
    stroke_width=1.0,
    radius=0,
    box=Style(fill="none", stroke="#111111", stroke_width=1.0, radius=0),
    arrow=Style(stroke="#111111", stroke_width=1.0, head="open", head_size=8),
    panel=Style(stroke="#aaaaaa", stroke_width=0.8, radius=0),
    styles={
        "block": Style(fill="none", stroke="#111111", stroke_width=1.4),
        "blue": Style(fill="none", stroke="#3B6EA5", stroke_width=1.4),
        "green": Style(fill="none", stroke="#3E7C4B", stroke_width=1.4),
        "warm": Style(fill="none", stroke="#B5622A", stroke_width=1.4),
        "ghost": Style(fill="none", stroke="#aaaaaa", stroke_dash="dashed"),
        "plain": Style(fill="none", stroke="none"),
        "card": Style(fill="none", stroke="#cccccc", radius=0),
    },
)

#: Rounded pastel cards with soft shadows, for product / blog diagrams.
SOFT = DEFAULT_THEME.derive(
    name="soft",
    font_size=14,
    radius=12,
    stroke_width=1.0,
    palette={"surface": "#ffffff", "surface_alt": "#f6f7f9",
             "primary": "#6366f1", "primary_soft": "#e0e7ff",
             "accent": "#f97316", "accent_soft": "#ffedd5",
             "good": "#10b981", "good_soft": "#d1fae5", "line": "#64748b"},
    box=Style(fill="#ffffff", stroke="#e2e5ea", stroke_width=1.0, radius=12,
              padding=(12, 16), shadow={"dy": 2, "blur": 6, "opacity": 0.12}),
    arrow=Style(stroke="#94a3b8", stroke_width=1.6, head="stealth"),
    panel=Style(fill="#f6f7f9", stroke="none", radius=16, padding=20),
    styles={
        "block": Style(fill="#f6f7f9", stroke="#e2e5ea"),
        "blue": Style(fill="#e0e7ff", stroke="#c7d2fe"),
        "green": Style(fill="#d1fae5", stroke="#a7f3d0"),
        "warm": Style(fill="#ffedd5", stroke="#fed7aa"),
    },
)

THEMES = {
    "default": DEFAULT_THEME, "figkit": DEFAULT_THEME,
    "paper": PAPER, "slide": SLIDE, "dark": DARK,
    "blueprint": BLUEPRINT, "minimal": MINIMAL, "soft": SOFT,
}


def get_theme(name) -> Theme:
    """Look up a built-in theme by name (or pass a Theme straight through)."""
    if isinstance(name, Theme):
        return name
    key = str(name).lower()
    if key not in THEMES:
        raise KeyError(f"unknown theme {name!r}; available: {sorted(THEMES)}")
    return THEMES[key]
