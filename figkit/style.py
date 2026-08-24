"""Styles and themes.

A :class:`Style` is a plain bag of visual properties where ``None`` means
"unset" (inherit).  A :class:`Theme` bundles *base tokens* (apply to any
element that understands the property), *role overrides* (per component kind),
a *palette* of named colours and a set of *named styles*.

Resolution order for a property, innermost first:

1. keyword arguments passed to the element (``Box(fill="red")``)
2. the element's own ``style=``
3. inherited text properties from enclosing groups (font, colour, ...)
4. themes attached to the element / its ancestors: role override, then base
5. the default theme
6. a hard-coded fallback
"""

from __future__ import annotations

import contextvars
from typing import Any, Iterable, Mapping

from .colors import parse_color, to_hex

__all__ = ["Style", "Theme", "DEFAULT_THEME", "use_theme", "current_theme",
           "INHERITED", "ALIASES", "PROPS", "register_props", "UnknownProperty"]


# --------------------------------------------------------------------------
# Property names & aliases
# --------------------------------------------------------------------------

#: Properties that cascade from a group's ``style`` down to its children.
INHERITED = frozenset({
    "font_family", "font_size", "font_weight", "font_style", "font_variant",
    "color", "line_height", "letter_spacing", "word_spacing", "text_align",
    "valign", "text_transform", "math_color", "math_scale",
})

#: Every property figkit reads. A name outside this set is a mistake, not an
#: extension: it would be accepted, stored and never looked at again, which is
#: indistinguishable from the property having no effect. Components that want
#: properties of their own add them with :func:`register_props`.
PROPS = {
    # paint
    "fill", "fill_opacity", "stroke", "stroke_width", "stroke_opacity",
    "stroke_dash", "stroke_dashoffset", "stroke_linecap", "stroke_linejoin",
    "opacity", "shadow", "background", "image_opacity",
    # geometry
    "radius", "padding",
    # type
    "font_family", "font_size", "font_weight", "font_style", "font_variant",
    "color", "line_height", "letter_spacing", "word_spacing", "text_align",
    "valign", "text_transform", "text_decoration",
    # math
    "math_backend", "math_color", "math_scale",
    # connectors
    "head", "head_size", "tail", "tail_size",
}


class UnknownProperty(TypeError):
    """Raised for a style property figkit would silently ignore."""


def register_props(*names: str) -> None:
    """Declare extra style properties, for components that read their own.

    ``Style`` rejects unknown properties, so a component with a property of
    its own registers it once::

        class Waveform(Component):
            ...
        register_props("wave_amplitude")
    """
    for name in names:
        PROPS.add(str(name).strip().lower().replace("-", "_"))


def _reject_unknown(key: str, raw_key: str) -> None:
    import difflib

    near = difflib.get_close_matches(key, PROPS | set(ALIASES), n=3, cutoff=0.6)
    hint = f" Did you mean {' or '.join(repr(n) for n in near)}?" if near else ""
    raise UnknownProperty(
        f"{raw_key!r} is not a figkit style property, and setting it would "
        f"have no effect.{hint} Use register_props({key!r}) if a component of "
        f"yours reads it.")


#: Friendly aliases -> canonical property name.
ALIASES = {
    "bg": "fill", "background": "fill", "background_color": "fill",
    "fill_color": "fill", "facecolor": "fill",
    "border": "stroke", "border_color": "stroke", "stroke_color": "stroke",
    "line_color": "stroke", "edgecolor": "stroke",
    "border_width": "stroke_width", "lw": "stroke_width",
    "linewidth": "stroke_width", "stroke_w": "stroke_width",
    "dash": "stroke_dash", "dashes": "stroke_dash",
    "dasharray": "stroke_dash", "stroke_dasharray": "stroke_dash",
    "linestyle": "stroke_dash", "ls": "stroke_dash",
    "cap": "stroke_linecap", "linecap": "stroke_linecap",
    "join": "stroke_linejoin", "linejoin": "stroke_linejoin",
    "corner_radius": "radius", "border_radius": "radius", "rounding": "radius",
    "text_color": "color", "fg": "color", "foreground": "color",
    "size": "font_size", "fontsize": "font_size",
    "font": "font_family", "fontfamily": "font_family",
    "family": "font_family", "typeface": "font_family",
    "weight": "font_weight", "fontweight": "font_weight",
    "fontstyle": "font_style",
    "align": "text_align", "halign": "text_align", "ha": "text_align",
    "va": "valign", "vertical_align": "valign",
    "alpha": "opacity",
    "leading": "line_height", "linespacing": "line_height",
    "tracking": "letter_spacing",
    "arrowhead": "head", "arrowtail": "tail",
    "headsize": "head_size", "tailsize": "tail_size",
}

#: Booleans that expand into a real property value.
#: flag name -> (property, value when True, value when False or None to skip)
_FLAGS = {
    "bold": ("font_weight", "bold", "normal"),
    "italic": ("font_style", "italic", "normal"),
    "underline": ("text_decoration", "underline", "none"),
    "monospace": ("font_family", "ui-monospace, SFMono-Regular, Menlo, "
                  "Consolas, monospace", None),
}

_DASH_PRESETS = {
    "solid": None, "-": None,
    "dashed": "6 4", "--": "6 4",
    "dotted": "1.5 3", ":": "1.5 3", ".": "1.5 3",
    "dashdot": "6 3 1.5 3", "-.": "6 3 1.5 3",
    "loose": "2 6", "tight": "3 2",
}


def normalize_key(key: str) -> str:
    k = str(key).strip().lower().replace("-", "_")
    return ALIASES.get(k, k)


def normalize_props(props: Mapping) -> dict:
    """Canonicalise keys, expand flags and dash presets, drop ``None`` values."""
    out: dict = {}
    for raw_key, value in props.items():
        key = str(raw_key).strip().lower().replace("-", "_")
        if key in _FLAGS:
            prop, on_val, off_val = _FLAGS[key]
            if value is True:
                out[prop] = on_val
            elif value is False:
                if off_val is not None:
                    out[prop] = off_val
            elif value is not None:
                out[prop] = value        # e.g. bold=600 or italic="oblique"
            continue
        key = ALIASES.get(key, key)
        if key not in PROPS:
            _reject_unknown(key, raw_key)
        if value is None:
            continue
        if key == "stroke_dash":
            value = normalize_dash(value)
            if value is None:
                out[key] = None
                continue
        out[key] = value
    return out


def normalize_dash(value) -> str | None:
    """Turn ``True``/preset names/number sequences into an SVG dasharray."""
    if value is None or value is False:
        return None
    if value is True:
        return "6 4"
    if isinstance(value, (int, float)):
        return f"{value} {value}"
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    s = str(value).strip()
    low = s.lower()
    if low in _DASH_PRESETS:
        return _DASH_PRESETS[low]
    return s


class Style(Mapping):
    """An immutable bag of visual properties.

    ``Style(fill="red") | Style(stroke="black")`` merges (right wins).
    A property figkit does not read raises :class:`UnknownProperty` rather
    than being kept and ignored; :func:`register_props` declares your own.
    """

    __slots__ = ("_props",)

    def __init__(self, *bases, **props):
        merged: dict = {}
        for base in bases:
            if base is None:
                continue
            if isinstance(base, Style):
                merged.update(base._props)
            elif isinstance(base, Mapping):
                merged.update(normalize_props(base))
            else:
                raise TypeError(f"cannot merge {base!r} into a Style")
        merged.update(normalize_props(props))
        object.__setattr__(self, "_props", merged)

    # -- mapping protocol ----------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self._props[normalize_key(key)]

    def __iter__(self):
        return iter(self._props)

    def __len__(self) -> int:
        return len(self._props)

    def __contains__(self, key) -> bool:
        return normalize_key(key) in self._props

    def get(self, key: str, default=None):
        return self._props.get(normalize_key(key), default)

    # -- merging --------------------------------------------------------
    def merge(self, *others) -> "Style":
        """Return a new style with ``others`` layered on top (later wins)."""
        return Style(self, *others)

    def __or__(self, other) -> "Style":
        return Style(self, other)

    def __ror__(self, other) -> "Style":
        return Style(other, self)

    def __add__(self, other) -> "Style":
        return Style(self, other)

    def updated(self, **props) -> "Style":
        return Style(self, **props)

    def only(self, keys: Iterable[str]) -> "Style":
        keep = {normalize_key(k) for k in keys}
        return Style({k: v for k, v in self._props.items() if k in keep})

    def without(self, keys: Iterable[str]) -> "Style":
        drop = {normalize_key(k) for k in keys}
        return Style({k: v for k, v in self._props.items() if k not in drop})

    def inherited(self) -> "Style":
        """Just the properties that cascade to children."""
        return self.only(INHERITED)

    # -- attribute access is handy in user code -------------------------
    def __getattr__(self, key: str):
        props = object.__getattribute__(self, "_props")
        k = normalize_key(key)
        if k in props:
            return props[k]
        raise AttributeError(key)

    def __setattr__(self, key, value):
        raise AttributeError("Style is immutable; use style.updated(**props)")

    def __eq__(self, other) -> bool:
        return isinstance(other, Style) and self._props == other._props

    def __hash__(self) -> int:
        return hash(tuple(sorted((k, repr(v)) for k, v in self._props.items())))

    # Styles are immutable and shared, so copying one can just hand it back.
    def __copy__(self) -> "Style":
        return self

    def __deepcopy__(self, memo) -> "Style":
        return self

    def __reduce__(self):
        return (Style, (dict(self._props),))

    def __repr__(self) -> str:
        inner = ", ".join(f"{k}={v!r}" for k, v in sorted(self._props.items()))
        return f"Style({inner})"


EMPTY_STYLE = Style()


class Theme:
    """A cascading bundle of defaults.

    ``Theme(fill="#eee", radius=10, box=Style(stroke="black"))``

    Any keyword whose value is a :class:`Style` or ``dict`` becomes a *role*
    override; everything else becomes a *base token* shared by all roles.
    """

    def __init__(self, *bases, name: str = None, palette: Mapping = None,
                 styles: Mapping = None, roles: Mapping = None, **props):
        self.name = name
        base: dict = {}
        self.roles: dict = {}
        self.palette: dict = {}
        self.styles: dict = {}
        self.parent: Theme | None = None

        for b in bases:
            if b is None:
                continue
            if isinstance(b, Theme):
                base.update(b.base._props)
                for r, s in b.roles.items():
                    self.roles[r] = Style(self.roles.get(r), s)
                self.palette.update(b.palette)
                self.styles.update(b.styles)
            elif isinstance(b, Mapping):
                base.update(normalize_props(b))
            else:
                raise TypeError(f"cannot merge {b!r} into a Theme")

        for key, value in list(props.items()):
            if isinstance(value, (Style, dict)) and not _looks_like_value(key):
                role = str(key).lower()
                self.roles[role] = Style(self.roles.get(role), value)
                props.pop(key)
        base.update(normalize_props(props))
        self.base = Style(base)

        for r, s in (roles or {}).items():
            self.roles[str(r).lower()] = Style(self.roles.get(str(r).lower()), s)
        self.palette.update({str(k): v for k, v in (palette or {}).items()})
        self.styles.update({str(k).lstrip("."): Style(v)
                            for k, v in (styles or {}).items()})

    # -- derivation -----------------------------------------------------
    def derive(self, **kw) -> "Theme":
        """A child theme layered on top of this one."""
        return Theme(self, **kw)

    __call__ = derive

    def role_style(self, role: str) -> Style:
        """Base tokens plus the role override, as one style."""
        return Style(self.base, self.roles.get(str(role).lower()))

    # -- lookups --------------------------------------------------------
    def lookup(self, prop: str, role: str = None):
        """Find ``prop`` for ``role``: role override first, then base tokens."""
        key = normalize_key(prop)
        if role:
            r = self.roles.get(str(role).lower())
            if r is not None and key in r:
                return r[key], True
        if key in self.base:
            return self.base[key], True
        return None, False

    def color(self, token: str, default=None):
        """Resolve a palette token (``"primary"`` or ``"@primary"``)."""
        name = str(token)[1:] if str(token).startswith("@") else str(token)
        if name in self.palette:
            return self.palette[name]
        return default if default is not None else token

    def resolve_value(self, value):
        """Expand ``"@token"`` colour references against the palette."""
        if isinstance(value, str) and value.startswith("@"):
            return self.color(value)
        return value

    def named(self, name: str) -> Style:
        if name not in self.styles:
            raise KeyError(f"unknown named style {name!r}; "
                           f"theme defines {sorted(self.styles)}")
        return self.styles[name]

    def with_styles(self, **styles) -> "Theme":
        return Theme(self, styles={k: Style(v) for k, v in styles.items()})

    # Themes are shared configuration, not per-element state: never clone them.
    def __copy__(self) -> "Theme":
        return self

    def __deepcopy__(self, memo) -> "Theme":
        return self

    def __repr__(self) -> str:
        return (f"Theme(name={self.name!r}, roles={sorted(self.roles)}, "
                f"base={self.base!r})")


def _looks_like_value(key: str) -> bool:
    """Guard so ``Theme(shadow={...})``-style value dicts aren't read as roles."""
    return normalize_key(key) in {"shadow", "gradient", "filter", "clip"}


# --------------------------------------------------------------------------
# Built-in defaults
# --------------------------------------------------------------------------

SANS = ("Inter, 'Helvetica Neue', Helvetica, Arial, "
        "'Liberation Sans', sans-serif")
SERIF = "'Latin Modern Roman', Georgia, 'Times New Roman', Times, serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"

#: Fallback values used when nothing in the cascade supplies a property.
FALLBACKS = {
    "fill": "none",
    "stroke": "none",
    "stroke_width": 1.0,
    "stroke_dash": None,
    "stroke_linecap": "butt",
    "stroke_linejoin": "miter",
    "opacity": 1.0,
    "fill_opacity": None,
    "stroke_opacity": None,
    "radius": 0,
    "color": "#111111",
    "font_family": SANS,
    "font_size": 14.0,
    "font_weight": "normal",
    "font_style": "normal",
    "line_height": 1.28,
    "letter_spacing": 0.0,
    "text_align": "center",
    "valign": "center",
    "padding": 0,
    "head": "triangle",
    "head_size": 9.0,
    "tail": None,
    "tail_size": 9.0,
}

DEFAULT_THEME = Theme(
    name="figkit",
    font_family=SANS,
    font_size=14,
    color="#16181d",
    line_height=1.3,
    stroke_width=1.4,
    radius=6,
    palette={
        "text": "#16181d",
        "muted": "#6b7280",
        "line": "#3f4450",
        "surface": "#ffffff",
        "surface_alt": "#f3f4f6",
        "primary": "#4C72B0",
        "primary_soft": "#dbe6f6",
        "accent": "#DD8452",
        "accent_soft": "#fbe4d5",
        "good": "#55A868",
        "good_soft": "#dcefe1",
        "bad": "#C44E52",
        "warn": "#CCB974",
    },
    box=Style(fill="#ffffff", stroke="#3f4450", stroke_width=1.4,
              padding=(8, 12), text_align="center", valign="center"),
    text=Style(fill=None, stroke=None, text_align="center", valign="center"),
    label=Style(fill=None, stroke=None, font_size=12, color="#16181d"),
    ellipse=Style(fill="#ffffff", stroke="#3f4450"),
    path=Style(fill="none", stroke="#3f4450", stroke_linejoin="round",
               stroke_linecap="round"),
    line=Style(fill="none", stroke="#3f4450", stroke_linecap="round"),
    arrow=Style(fill="none", stroke="#3f4450", stroke_width=1.6,
                stroke_linecap="round", stroke_linejoin="round",
                head="triangle", head_size=9),
    panel=Style(fill="none", stroke="#9aa1ac", stroke_width=1.2, radius=8,
                padding=16),
    group=Style(),
    image=Style(),
    matrix=Style(stroke="#ffffff", stroke_width=0.75, radius=0),
    brace=Style(fill="none", stroke="#3f4450", stroke_width=1.4),
    axis=Style(fill="none", stroke="#6b7280", stroke_width=1.0),
    grid=Style(fill="none", stroke="#e5e7eb", stroke_width=1.0),
    marker=Style(fill="#4C72B0", stroke="none"),
    styles={
        "block": Style(fill="#f3f4f6", stroke="#2b2f36", stroke_width=1.6,
                       radius=4),
        "blue": Style(fill="#cfe3f7", stroke="#3a6ea5", stroke_width=1.4,
                      radius=6),
        "slate": Style(fill="#b9c7d6", stroke="#5a6b7d", stroke_width=1.4,
                       radius=6),
        "green": Style(fill="#cfe9d4", stroke="#4a8759", stroke_width=1.4,
                       radius=6),
        "warm": Style(fill="#fbe4d5", stroke="#c2703c", stroke_width=1.4,
                      radius=6),
        "ghost": Style(fill="none", stroke="#9aa1ac", stroke_width=1.2,
                       stroke_dash="dashed", radius=8),
        "plain": Style(fill="none", stroke="none"),
        "card": Style(fill="#ffffff", stroke="#e3e6ea", stroke_width=1,
                      radius=12, shadow=True),
    },
)


# --------------------------------------------------------------------------
# Ambient theme (used when an element has no theme and no figure yet)
# --------------------------------------------------------------------------

# A ContextVar rather than a module global: concurrent threads and asyncio
# tasks each get their own ambient theme instead of trampling one stack.
_theme_var: contextvars.ContextVar = contextvars.ContextVar("figkit_theme",
                                                            default=None)


def current_theme() -> Theme:
    """The theme in effect right now (see :class:`use_theme`)."""
    return _theme_var.get() or DEFAULT_THEME


class use_theme:
    """Context manager to set the ambient theme.

    >>> with use_theme(my_theme):
    ...     b = Box("hi")
    """

    def __init__(self, theme: Theme):
        self.theme = theme if isinstance(theme, Theme) else Theme(theme)
        self._token = None

    def __enter__(self) -> Theme:
        self._token = _theme_var.set(self.theme)
        return self.theme

    def __exit__(self, *exc):
        if self._token is not None:
            _theme_var.reset(self._token)
            self._token = None
        return False


def resolve_color(value, theme: Theme = None):
    """Expand palette tokens and normalise to something SVG understands."""
    if value is None:
        return None
    if isinstance(value, str):
        if value.startswith("@") and theme is not None:
            value = theme.color(value)
        if isinstance(value, str) and (value.startswith("url(")
                                       or value.lower() == "none"
                                       or value.startswith("var(")):
            return value
    if isinstance(value, (tuple, list)):
        return to_hex(value)
    if isinstance(value, str):
        try:
            parse_color(value)
        except ValueError:
            return value
    return value
