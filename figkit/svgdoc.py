"""Minimal SVG node tree + the render context shared by all elements."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .svgpath import fmt

__all__ = ["Node", "RenderContext", "esc", "attrs_to_str"]

_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"),
            ('"', "&quot;"), ("'", "&apos;"))


def esc(text) -> str:
    """Escape text for XML content/attributes."""
    s = str(text)
    for a, b in _ESCAPES:
        s = s.replace(a, b)
    return s


def attrs_to_str(attrs: dict) -> str:
    parts = []
    for k, v in attrs.items():
        if v is None:
            continue
        key = k.replace("__", ":") if "__" in k else k.replace("_", "-")
        if isinstance(v, bool):
            v = "true" if v else "false"
        elif isinstance(v, (int, float)):
            v = fmt(v)
        parts.append(f'{key}="{esc(v)}"')
    return " ".join(parts)


class Node:
    """An SVG element in the output tree."""

    __slots__ = ("tag", "attrs", "children", "text", "raw")

    def __init__(self, tag: str, text: str = None, raw: str = None, **attrs):
        self.tag = tag
        self.attrs = {k: v for k, v in attrs.items() if v is not None}
        self.children: list = []
        self.text = text
        self.raw = raw            # verbatim XML inserted as-is

    def add(self, *nodes) -> "Node":
        for n in nodes:
            if n is None:
                continue
            if isinstance(n, (list, tuple)):
                self.add(*n)
            else:
                self.children.append(n)
        return self

    def set(self, **attrs) -> "Node":
        for k, v in attrs.items():
            if v is None:
                self.attrs.pop(k, None)
            else:
                self.attrs[k] = v
        return self

    @property
    def empty(self) -> bool:
        return not self.children and self.text is None and self.raw is None

    def render(self, indent: int = 0, pretty: bool = True) -> str:
        pad = "  " * indent if pretty else ""
        nl = "\n" if pretty else ""
        a = attrs_to_str(self.attrs)
        open_tag = f"{pad}<{self.tag}{' ' + a if a else ''}"
        if self.empty:
            return f"{open_tag}/>{nl}"
        inner_parts = []
        if self.text is not None:
            inner_parts.append(esc(self.text))
        if self.raw is not None:
            inner_parts.append(self.raw)
        child_text = "".join(inner_parts)
        if self.children:
            body = "".join(c.render(indent + 1, pretty) for c in self.children)
            return (f"{open_tag}>{child_text}{nl}{body}{pad}</{self.tag}>{nl}")
        # text-only node: keep on one line so <text> whitespace stays exact
        return f"{open_tag}>{child_text}</{self.tag}>{nl}"

    def __repr__(self) -> str:
        return f"<Node {self.tag} {len(self.children)} children>"


@dataclass
class RenderContext:
    """Carries shared state (defs, ids, options) through one render pass."""

    theme: object = None
    text_as_paths: bool = False
    embed_fonts: bool = False
    math_backend: str = "auto"
    pretty: bool = True
    precision: int = 4
    defs: list = field(default_factory=list)
    _def_keys: dict = field(default_factory=dict)
    _counter: dict = field(default_factory=dict)
    fonts_used: set = field(default_factory=set)
    warnings: list = field(default_factory=list)

    def uid(self, prefix: str = "fk") -> str:
        n = self._counter.get(prefix, 0) + 1
        self._counter[prefix] = n
        return f"{prefix}{n}"

    def add_def(self, node: Node, key: str = None) -> str:
        """Add a node to ``<defs>``, de-duplicating by ``key``. Returns its id."""
        if key is None:
            key = hashlib.md5(node.render(0, False).encode()).hexdigest()[:12]
        if key in self._def_keys:
            return self._def_keys[key]
        node_id = node.attrs.get("id") or self.uid("d")
        node.attrs["id"] = node_id
        self._def_keys[key] = node_id
        self.defs.append(node)
        return node_id

    def note_font(self, family, weight, style) -> None:
        self.fonts_used.add((family, weight, style))

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
