"""Reusable components with named anchors.

A plain function returning a :class:`~figkit.core.Group` already gets you a
reusable unit. What it cannot do is *name* the interesting points on that
unit, so callers end up reaching into ``group.children[1]``. A
:class:`Component` builds itself and publishes the anchors that matter:

    class PortBlock(Component):
        def build(self, label):
            body = Box(label, w=120)
            self.expose("port", body.e)
            self.expose("body", body)
            return [body]

    block = PortBlock("filter")
    arrow(source.e, block.port)      # a live anchor, like any other
"""

from __future__ import annotations

from .core import Element, Group

__all__ = ["Component"]

#: Constructor arguments that belong to the Group, not to ``build()``.
_GROUP_KEYS = ("style", "classes", "theme", "name", "z", "visible", "opacity",
               "clip", "audit", "add")


class Component(Group):
    """Base class for a reusable group that publishes named anchors.

    Subclasses implement :meth:`build`, returning the elements to hold, and
    call :meth:`expose` for anything callers should be able to point at.
    Group keyword arguments (``name``, ``z``, ``theme``, ``style``, …) are
    understood by the constructor and never reach ``build()``.
    """

    def __init__(self, *args, **kwargs):
        group_kwargs = {k: kwargs.pop(k) for k in _GROUP_KEYS if k in kwargs}
        self._exposed: dict = {}
        super().__init__(**group_kwargs)
        children = self.build(*args, **kwargs)
        if children is None:
            children = []
        elif isinstance(children, Element):
            children = [children]
        self.add(*children)

    # -- subclass hook ---------------------------------------------------
    def build(self, *args, **kwargs):
        """Create and return this component's elements.

        Called once from the constructor with whatever positional and keyword
        arguments were not consumed as group options.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement build()")

    # -- named anchors ---------------------------------------------------
    def expose(self, name: str, target) -> "Component":
        """Publish ``target`` under ``name``.

        ``target`` may be an :class:`~figkit.core.Anchor` (``body.e``), an
        element (exposed as itself), or a callable returning either — use a
        callable when the answer depends on state that changes later.
        """
        if name in _RESERVED:
            raise ValueError(f"{name!r} is reserved; pick another anchor name")
        self._exposed[str(name)] = target
        return self

    @property
    def exposed(self) -> tuple:
        """The names this component publishes."""
        return tuple(self._exposed)

    def anchor(self, name: str):
        """Named anchors first, then the usual bounding-box anchors."""
        if name in self._exposed:
            return self._resolve(name)
        return super().anchor(name)

    def _resolve(self, name: str):
        target = self._exposed[name]
        return target() if callable(target) else target

    def __getattr__(self, name: str):
        # only reached when normal attribute lookup fails
        exposed = self.__dict__.get("_exposed")
        if exposed and name in exposed:
            target = exposed[name]
            return target() if callable(target) else target
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}")

    def __repr__(self) -> str:
        bb = self.bbox
        names = ", ".join(self.exposed)
        return (f"<{type(self).__name__} {len(self._children)} children "
                f"[{names}] x={bb.x:.4g} y={bb.y:.4g} "
                f"w={bb.w:.4g} h={bb.h:.4g}>")


#: Names that would shadow the Element API if exposed.
_RESERVED = frozenset({
    "n", "s", "e", "w", "ne", "nw", "se", "sw", "c", "center", "bbox", "parent",
    "style", "theme", "children", "point", "top", "bottom", "left", "right",
    "build", "expose", "exposed", "anchor", "add", "move", "at",
})
