# Contributing to figkit

Thanks for taking a look. Bug reports with a short reproduction are the most
useful thing you can send.

## Getting set up

```bash
git clone https://github.com/philippspohn/figkit
cd figkit
pip install -e ".[dev]"
pytest
```

The test suite runs in a few seconds and needs no network access. `cairosvg`
and `matplotlib` are optional: without them the PNG/PDF and `$math$` tests
skip rather than fail.

## What the tests expect

- **Every example must audit clean.** `tests/test_examples.py` runs each
  script in `examples/` and asserts `fig.audit()` reports nothing. If you add
  an example, it has to pass that.
- **The audit's quiet half matters most.** `tests/test_audit.py` has as many
  "stays quiet about this" cases as "catches this" ones. A checker that
  reports intentional overlap is worse than no checker, so new checks need
  tests on both sides.
- **Geometry tests should be geometric.** Assert the property (this stroke
  ends on the head's axis), not the string that happens to come out today.

## House style

- Follow the surrounding code: standard library only in the core, postponed
  annotations everywhere, and no third-party imports outside the optional
  extras.
- Comments explain *why*, not *what*. If a line needs a comment to say what it
  does, it usually wants renaming instead.
- Public functions get a docstring with a one-line summary and, where it
  helps, a short example.
- Run `python -m pyflakes figkit` before opening a pull request.

## Things worth knowing before changing the internals

- Anchors are lazy; placements are eager. `arrow(a.e, b.w)` tracks forever,
  `a.align_to(b)` happens once.
- All public geometry is in world coordinates. Containers that position their
  own labels use `Element.place_local` for parent-space arithmetic instead.
- `Group` takes ownership of its children. `bbox_of([...])` is the read-only
  way to ask about a set of elements.
