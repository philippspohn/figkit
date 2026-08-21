"""Embedding raster images and external SVGs."""

from __future__ import annotations

import base64
import os
import re
import struct
import xml.etree.ElementTree as ET

from .core import Element
from .geom import Affine, BBox
from .svgdoc import Node, RenderContext

__all__ = ["Image", "image_size", "SVGFile"]

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
         ".svg": "image/svg+xml", ".avif": "image/avif"}

_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"


def image_size(data: bytes, path: str = "") -> tuple:
    """Sniff ``(width, height)`` from raw image bytes. ``(None, None)`` if unknown."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return float(w), float(h)
    if data[:2] == b"\xff\xd8":                       # JPEG
        i = 2
        n = len(data)
        while i < n - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return float(w), float(h)
            i += 2 + seg_len
        return None, None
    if data[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", data[6:10])
        return float(w), float(h)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return float(w), float(h)
        if chunk == b"VP8 ":
            w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return float(w), float(h)
        if chunk == b"VP8L":
            b = data[21:25]
            bits = int.from_bytes(b, "little")
            return float((bits & 0x3FFF) + 1), float(((bits >> 14) & 0x3FFF) + 1)
        return None, None
    if data[:2] == b"BM":
        w, h = struct.unpack("<ii", data[18:26])
        return float(abs(w)), float(abs(h))
    head = data[:4096].decode("utf-8", "ignore")
    if "<svg" in head or path.lower().endswith(".svg"):
        return _svg_size(data.decode("utf-8", "ignore"))
    return None, None


_LEN_RE = re.compile(r"^\s*(-?[\d.]+)\s*([a-z%]*)\s*$", re.I)
_UNITS = {"": 1.0, "px": 1.0, "pt": 96 / 72, "pc": 16.0, "mm": 96 / 25.4,
          "cm": 96 / 2.54, "in": 96.0}


def _length(value, default=None):
    if value is None:
        return default
    m = _LEN_RE.match(str(value))
    if not m:
        return default
    unit = m.group(2).lower()
    if unit == "%":
        return default
    return float(m.group(1)) * _UNITS.get(unit, 1.0)


def _svg_size(text: str) -> tuple:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None, None
    w = _length(root.get("width"))
    h = _length(root.get("height"))
    vb = root.get("viewBox")
    if vb:
        parts = [float(x) for x in re.split(r"[,\s]+", vb.strip()) if x]
        if len(parts) == 4:
            if w is None:
                w = parts[2]
            if h is None:
                h = parts[3]
    return w, h


class Image(Element):
    """Place a PNG/JPEG/GIF/WebP or SVG file into the figure.

    Raster images are base64-embedded so the exported SVG is self-contained.
    SVG files are inlined as vectors by default (``inline=True``), with all
    internal ids rewritten so several copies never collide.

    >>> Image("logo.svg", w=80)
    >>> Image("plot.png", w=200).right_of(box, gap=20)
    """

    role = "image"

    def __init__(self, source, x: float = 0.0, y: float = 0.0, w: float = None,
                 h: float = None, *, inline: bool = True,
                 fit: str = "contain", mime: str = None, **kw):
        self.source = source
        self.inline = inline
        self.fit = fit
        self._mime = mime
        self._data: bytes | None = None
        self._text: str | None = None
        self._natural = (None, None)
        self._load()
        super().__init__(x, y, w, h, **kw)

    # -- loading ---------------------------------------------------------
    def _load(self) -> None:
        src = self.source
        if isinstance(src, bytes):
            self._data = src
            self._mime = self._mime or "image/png"
        elif isinstance(src, str) and src.startswith("data:"):
            header, _, payload = src.partition(",")
            self._mime = self._mime or header[5:].split(";")[0]
            try:
                self._data = base64.b64decode(payload)
            except Exception:
                self._data = payload.encode()
        elif isinstance(src, str) and src.lstrip().startswith("<svg"):
            self._text = src
            self._data = src.encode()
            self._mime = "image/svg+xml"
        else:
            path = os.fspath(src)
            if not os.path.isfile(path):
                raise FileNotFoundError(f"image not found: {path}")
            with open(path, "rb") as fh:
                self._data = fh.read()
            ext = os.path.splitext(path)[1].lower()
            self._mime = self._mime or _MIME.get(ext, "application/octet-stream")
        if self._mime == "image/svg+xml" and self._text is None:
            self._text = self._data.decode("utf-8", "ignore")
        self._natural = image_size(self._data, str(self.source)
                                   if isinstance(self.source, str) else "")

    @property
    def natural_size(self) -> tuple:
        return self._natural

    @property
    def is_svg(self) -> bool:
        return self._mime == "image/svg+xml"

    def _measure(self) -> None:
        nw, nh = self._natural
        nw = nw or 100.0
        nh = nh or 100.0
        if self._explicit_w and self._explicit_h:
            return
        if self._explicit_w:
            self._h = self._w * nh / nw
        elif self._explicit_h:
            self._w = self._h * nw / nh
        else:
            self._w, self._h = nw, nh

    def data_uri(self) -> str:
        b64 = base64.b64encode(self._data).decode("ascii")
        return f"data:{self._mime};base64,{b64}"

    # -- rendering -------------------------------------------------------
    def _render_content(self, ctx: RenderContext):
        self._ensure()
        bb = self.local_bbox
        if self.is_svg and self.inline:
            node = self._inline_svg(ctx, bb)
            if node is not None:
                return node
        par = {"contain": "xMidYMid meet", "cover": "xMidYMid slice",
               "fill": "none", "stretch": "none"}.get(self.fit, "xMidYMid meet")
        attrs = {"x": bb.x, "y": bb.y, "width": bb.w, "height": bb.h,
                 "preserveAspectRatio": par, "href": self.data_uri()}
        op = self.prop("image_opacity", None)
        if op is not None:
            attrs["opacity"] = op
        return Node("image", **attrs)

    def _inline_svg(self, ctx: RenderContext, bb: BBox):
        try:
            root = ET.fromstring(self._text)
        except ET.ParseError:
            ctx.warn(f"could not parse SVG {self.source!r}; embedding as image")
            return None
        nw, nh = self._natural
        vb = root.get("viewBox")
        if vb:
            parts = [float(x) for x in re.split(r"[,\s]+", vb.strip()) if x]
            vx, vy, vw, vh = parts if len(parts) == 4 else (0, 0, nw or bb.w,
                                                            nh or bb.h)
        else:
            vx, vy, vw, vh = 0.0, 0.0, nw or bb.w, nh or bb.h
        if not vw or not vh:
            return None
        scale = min(bb.w / vw, bb.h / vh) if self.fit == "contain" else \
            max(bb.w / vw, bb.h / vh) if self.fit == "cover" else None
        if scale is None:
            sx, sy = bb.w / vw, bb.h / vh
        else:
            sx = sy = scale
        tx = bb.x + (bb.w - vw * sx) / 2.0 - vx * sx
        ty = bb.y + (bb.h - vh * sy) / 2.0 - vy * sy
        prefix = ctx.uid("svg") + "_"
        ids = {el.get("id") for el in root.iter() if el.get("id")}
        body = "".join(_serialize(child, ids, prefix)
                       for child in root
                       if _localname(child.tag) not in ("title", "desc",
                                                        "metadata"))
        m = Affine(sx, 0, 0, sy, tx, ty)
        g = Node("g", raw=body)
        if not m.is_identity:
            g.attrs["transform"] = m.to_svg()
        return g


def _localname(tag) -> str:
    return tag.split("}")[-1] if isinstance(tag, str) else str(tag)


_URL_RE = re.compile(r"url\(\s*['\"]?#([^)'\"]+)['\"]?\s*\)")


def _serialize(el, ids: set, prefix: str) -> str:
    """Re-emit an XML subtree, namespacing ids so copies never collide."""
    tag = _localname(el.tag)
    parts = [f"<{tag}"]
    for key, value in el.attrib.items():
        k = _localname(key)
        if key.startswith(f"{{{_XLINK_NS}}}"):
            k = "href"
        if k in ("id",) and value in ids:
            value = prefix + value
        elif k == "href" and value.startswith("#") and value[1:] in ids:
            value = "#" + prefix + value[1:]
        elif "url(#" in str(value):
            value = _URL_RE.sub(
                lambda m: f"url(#{prefix + m.group(1) if m.group(1) in ids else m.group(1)})",
                value)
        if k.startswith("xmlns"):
            continue
        parts.append(f' {k}="{_xesc(value)}"')
    children = list(el)
    text = (el.text or "")
    if not children and not text.strip():
        parts.append("/>")
        return "".join(parts)
    parts.append(">")
    if tag == "style":
        parts.append(_URL_RE.sub(
            lambda m: f"url(#{prefix + m.group(1) if m.group(1) in ids else m.group(1)})",
            text))
    else:
        parts.append(_xesc_text(text))
    for child in children:
        parts.append(_serialize(child, ids, prefix))
        if child.tail:
            parts.append(_xesc_text(child.tail))
    parts.append(f"</{tag}>")
    return "".join(parts)


def _xesc(v) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _xesc_text(v) -> str:
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


SVGFile = Image
