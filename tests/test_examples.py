"""Smoke test: every example must run, emit valid SVG, and audit clean.

Each script is executed once, in a temporary working directory, and both
checks are made against that single run — examples write files, so running
them twice is wasteful and (when an export backend is missing) doubles the
noise from a single failure.
"""

import os
import runpy
import warnings
import xml.etree.ElementTree as ET

import pytest

from figkit.mathtext import math_available

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE_DIR = os.path.join(ROOT, "examples")
EXAMPLES = sorted(f for f in os.listdir(EXAMPLE_DIR) if f.endswith(".py"))


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """Run every example once; yield {name: (figure, output_dir)}."""
    out = {}
    for name in EXAMPLES:
        work = tmp_path_factory.mktemp(name.replace(".py", ""))
        cwd = os.getcwd()
        os.chdir(work)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                namespace = runpy.run_path(os.path.join(EXAMPLE_DIR, name),
                                           run_name="__figkit_example__")
        finally:
            os.chdir(cwd)
        out[name] = (namespace.get("fig"), work)
    return out


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_writes_valid_svg(name, rendered):
    _figure, work = rendered[name]
    svgs = list((work / "out").glob("*.svg"))
    assert svgs, f"{name} produced no SVG"
    for svg in svgs:
        text = svg.read_text()
        root = ET.fromstring(text[text.index("<svg"):])
        assert root.tag.endswith("svg")
        assert float(root.get("width").rstrip("px")) > 0


@pytest.mark.skipif(
    not math_available(),
    reason="the examples use $math$; without matplotlib it degrades to literal "
           "TeX source, which is wider and legitimately collides")
@pytest.mark.parametrize("name", EXAMPLES)
def test_example_audits_clean(name, rendered):
    """The shipped examples must not trip figkit's own checks."""
    figure, _work = rendered[name]
    assert figure is not None, f"{name} does not expose a `fig`"
    report = figure.audit()
    assert not report, str(report)
