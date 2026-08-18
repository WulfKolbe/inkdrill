"""Which modules the CLI can actually reach (A3).

A module can be built, tested, measured and correct, and still not run:
`mathstruct.group()` was fixed while unreachable from `__main__`, so a
downstream re-run was byte-identical and correctly so. Nothing failed,
because nothing was wrong -- the fix simply could not get to the file.

This test makes that visible at commit time. It is a WRITTEN DECISION,
not a snapshot: every module off the CLI path carries the reason it is
off it, so adding a module means stating which side it is on and why,
and wiring one in means deleting its reason.

Imports are read with `ast` rather than by importing, so a module with
an expensive import or an optional dependency cannot distort the graph.
"""

import ast
import pathlib
import unittest

_PKG = pathlib.Path(__file__).resolve().parents[1] / "inkdrill"

#: Modules deliberately NOT on the CLI path, each with its reason.
#: A reason is a claim about scope, and a wrong one is a bug report.
OFF_THE_CLI_PATH = {
    "band": "the parallel sweep tier; the CLI does one page at a time "
            "and U8's band tier was measured into the ground",
    "coverage": "cross-checks ANOTHER tool's regions, so it needs that "
                "tool's output as a second input the CLI does not take",
    "domains": "the Gardenfors design test; an analysis tool for adding "
               "a dimension, not a per-page step",
    "font": "font inventory from a PDF; the CLI reads a raster",
    "gold": "pdfminer alignment; needs the PDF, not the page image",
    "relate": "the maths layer; candidate edges need symbol identity "
              "downstream and nothing consumes them",
    "rewrite": "the maths layer; consumes `relate` output",
    "sched": "multi-page scheduling; the CLI is serial by design",
    "seam": "curved gutters; measured and not wired into `page_lines`",
    "space": "affine algebra used by the units above, not by emit",
    "trace": "boundary contours; nothing in lines.json carries a "
             "polygon yet, and the consumer has not asked for one",
    "typeface": "weight/slant/serif signals; measured, and no lines.json "
                "field carries them yet -- same standing as qc",
}


def _local_imports(path: pathlib.Path) -> set[str]:
    """Package-local modules imported by one file, by AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 1 and node.module:
                out.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("inkdrill."):
                    out.add(alias.name.split(".")[1])
    return out


def reachable_from(entry: str = "__main__") -> set[str]:
    seen: set[str] = set()
    stack = [entry]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        path = _PKG / f"{name}.py"
        if path.exists():
            stack.extend(_local_imports(path) - seen)
    return seen


class TA3_1_CliReachability(unittest.TestCase):

    def setUp(self):
        self.reach = reachable_from()
        self.all = {p.stem for p in _PKG.glob("*.py")
                    if p.stem != "__init__"}

    def test_every_module_is_on_one_side_or_the_other(self):
        """No module may be silently unlisted. Adding one forces the
        decision rather than deferring it to an integration phase."""
        unreached = self.all - self.reach
        self.assertEqual(
            unreached, set(OFF_THE_CLI_PATH),
            "a module is unreachable from the CLI with no recorded "
            "reason, or a recorded reason names a module that is now "
            "wired in")

    def test_mathstruct_is_WIRED_IN(self):
        """The case that motivated this file. `group()` turns components
        into glyphs -- `i`, `j`, `:`, umlauts -- and a `lines.json`
        written without it carries 2,125 components where a page has
        about 1,869 glyphs."""
        self.assertIn("mathstruct", self.reach)

    def test_the_emit_chain_is_reachable(self):
        """The spine, asserted explicitly rather than inferred from the
        absence of failures."""
        for name in ("emit", "nest", "sweep", "raster", "aggregate",
                     "pngio", "pnmio", "classify", "reeb", "version"):
            self.assertIn(name, self.reach, name)

    def test_a_reason_is_not_empty(self):
        """A blank reason would pass the set comparison while recording
        nothing, which is the failure mode this file exists to prevent
        one level up."""
        for name, why in OFF_THE_CLI_PATH.items():
            self.assertTrue(why.strip(), name)
            self.assertGreater(len(why), 20, name)


if __name__ == "__main__":
    unittest.main()
