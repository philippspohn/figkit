"""Smoke test: every example script must run and produce a valid SVG."""

import os
import runpy
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = sorted(f for f in os.listdir(os.path.join(ROOT, "examples"))
                  if f.endswith(".py"))


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_runs(name, tmp_path):
    script = os.path.join(ROOT, "examples", name)
    proc = subprocess.run([sys.executable, script],
                          cwd=str(tmp_path), capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": ROOT},
                          timeout=180)
    # examples write into ./out relative to the cwd
    assert proc.returncode == 0, proc.stderr[-2000:]
    out_dir = tmp_path / "out"
    svgs = list(out_dir.glob("*.svg"))
    assert svgs, "example produced no SVG"
    for svg in svgs:
        text = svg.read_text()
        root = ET.fromstring(text[text.index("<svg"):])
        assert root.tag.endswith("svg")
        assert float(root.get("width").rstrip("px")) > 0
