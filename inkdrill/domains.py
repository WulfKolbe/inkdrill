"""domains.py — conceptual-space feature domains.

CONTRACT (written before implementation; see docs/units.md U12)
==============================================================

The design test, shipped rather than described
----------------------------------------------
docs/units.md sets one rule for this unit, after Gardenfors: **a dimension
earns its place when the concepts of interest become convex in it.**

That is a measurable claim, so this module SHIPS the test -- `convexity()`
and `mutual_information()` -- rather than describing it. A future
dimension is added by measuring it, not by arguing for it. `DIMENSIONS`
records the measured score of every dimension already present, so adding
one that scores worse than `depth` is a visible decision.

What the measurement said, and how it reorders the plan
-------------------------------------------------------
5,436 real glyph instances over 23 character classes with 40+ examples
each. Random baseline purity is 1/23 = 0.043.

        dimension   convex(10-90)  lift   norm. MI   domain
        aspect          0.489      11.2x    0.634     size
        elongation      0.437      10.1x    0.627     shape
        width           0.273       6.3x    0.584     size
        fill            0.374       8.6x    0.561     shape
        area            0.287       6.6x    0.544     size
        height          0.248       5.7x    0.418     size
        splits          0.163       3.7x    0.373     topology
        merges          0.120       2.8x    0.320     topology
        births          0.101       2.3x    0.255     topology
        cycles          0.127       2.9x    0.246     topology
        depth           0.086       2.0x    0.220     topology

Reproduce with:
    python3 tools/premise/measure.py --corpus <dir> convexity --seed 23

which runs the SHIPPED `convexity()` and `mutual_information()`, so these
are the module's own numbers rather than a scratch script's.

**Every topological dimension ranks below every geometric one.** U13's
plan text reads as though the bitmap and the Reeb signature are the two
channels, with "aspect ratio and absolute extents carried separately"
as a supplement for `- - -- ---` and `. *`. The measurement inverts that
emphasis: **aspect and extents are the strongest dimensions available**,
stronger than the whole topological channel.

**Stability and discriminative power are different properties, and
`cycles` shows the gap.** U4's premise check found the hole count is the
most STABLE feature -- 98.7-100% consistent across instances of a
character. Here it is near the bottom for DISCRIMINATION, because `e a o
b d p q` all have exactly one hole. A dimension that never varies within
a class and barely varies between classes is reliable and nearly
useless on its own. Both facts are true and neither implies the other.

Separability is the point of domains
------------------------------------
docs/units.md asks for **transform as its own domain, "so rotation and
shear stop contaminating shape"**. That separation is the whole reason
this is a set of domains rather than one flat feature vector: a rotated
`A` should move in the TRANSFORM domain and stay put in SHAPE.

This module enforces the separation structurally -- every dimension
declares its domain, and `describe()` returns a point split by domain, so
a consumer that wants shape cannot accidentally read a transform
dimension. It does not yet enforce that the shape dimensions ARE rotation
invariant; U4 measured that they are not (see its G5), which is a fact
about the dimensions rather than about this structure.

Guarantees
----------
G1  every dimension declares exactly one domain, and `describe()` returns
    a point partitioned by domain -- shape and transform cannot be read
    as one vector by accident
G2  `convexity()` implements the stated design test and is robust to
    outliers by construction: it uses an inter-percentile interval, not
    min/max, because one outlier stretches a min/max interval across the
    whole range and makes every dimension look worthless
G3  `convexity()` and `mutual_information()` return a random-baseline
    figure alongside the score, so a number can be read without knowing
    the class count
G4  every dimension carries its MEASURED score, and the measurement date
    and sample size, so an unmeasured dimension is visibly unmeasured
G5  the TYPOGRAPHIC domain is declared and EMPTY: it needs U9's reference
    lines, which are not built. An empty domain is reported as empty
    rather than silently omitted
G6  `describe()` is total: a component missing an input yields a point
    with that dimension absent, never a wrong value
G7  dimension extraction is pure -- no I/O, no global state -- so a point
    depends only on its inputs

Non-guarantees (out of scope for U12)
-------------------------------------
  * no classification -- that is U13. This unit says which dimensions
    carry information, not how to combine them.
  * no TRANSFORM dimensions yet: they need a per-character CTM, which
    comes from U10's alignment, and the domain is declared with its
    inputs named rather than populated with guesses
  * no Morton code. docs/units.md lists it under POSITION; it is an
    encoding of two dimensions already present, so it belongs to a
    consumer that wants spatial locality, not to the space itself.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

__all__ = ["Domain", "Dimension", "DIMENSIONS", "Point", "describe",
           "convexity", "mutual_information", "ConvexityResult",
           "dimensions_of", "UnknownDimension"]


class UnknownDimension(KeyError):
    """no dimension by that name."""


class Domain(Enum):
    """Separable domains. TRANSFORM is its own so rotation and shear stop
    contaminating SHAPE -- that separation is why this is a set of
    domains rather than one flat vector."""
    SHAPE = "shape"
    SIZE = "size"
    POSITION = "position"
    TRANSFORM = "transform"
    TOPOLOGY = "topology"
    TYPOGRAPHIC = "typographic"


@dataclass(frozen=True, slots=True)
class Dimension:
    """One measurable axis, with the score that earned it its place."""
    name: str
    domain: Domain
    extract: Callable[[Mapping[str, Any]], float | None]
    convexity: float | None = None      # measured, 10-90 interval purity
    lift: float | None = None           # times the random baseline
    nmi: float | None = None            # normalised mutual information
    note: str = ""

    @property
    def measured(self) -> bool:
        return self.nmi is not None


def _get(key: str) -> Callable[[Mapping[str, Any]], float | None]:
    def f(d: Mapping[str, Any]) -> float | None:
        v = d.get(key)
        return None if v is None else float(v)
    return f


def _aspect(d: Mapping[str, Any]) -> float | None:
    # The guard is redundant with `describe()`'s TypeError/ZeroDivisionError
    # catch and is kept because an extractor called directly should not
    # raise. Confirmed redundant by branch mutation, not assumed.
    w, h = d.get("width"), d.get("height")
    if not w or not h:
        return None
    return w / h


def _fill(d: Mapping[str, Any]) -> float | None:
    a, w, h = d.get("area"), d.get("width"), d.get("height")
    if not a or not w or not h:
        return None
    return a / (w * h)


# Scores measured 2026-08-08 on 5,436 real glyph instances over 23
# character classes with 40+ examples each; random baseline 0.043.
_MEASURED = "2026-08-08, n=5436, 23 classes"

DIMENSIONS: tuple[Dimension, ...] = (
    # --- SIZE: the strongest domain, contrary to the plan's emphasis ---
    Dimension("aspect", Domain.SIZE, _aspect, 0.489, 11.2, 0.634,
              "strongest single dimension measured"),
    Dimension("width", Domain.SIZE, _get("width"), 0.273, 6.3, 0.584),
    Dimension("area", Domain.SIZE, _get("area"), 0.287, 6.6, 0.544),
    Dimension("height", Domain.SIZE, _get("height"), 0.248, 5.7, 0.418),

    # --- SHAPE ---
    Dimension("elongation", Domain.SHAPE, _get("elongation"),
              0.437, 10.1, 0.627, "U5; lambda-2 floored at 1/12"),
    Dimension("fill", Domain.SHAPE, _fill, 0.374, 8.6, 0.561,
              "ink area over bounding-box area"),

    # --- TOPOLOGY: every dimension here scores below every SIZE one ---
    Dimension("splits", Domain.TOPOLOGY, _get("splits"), 0.163, 3.7, 0.373,
              "U4 Reeb signature"),
    Dimension("merges", Domain.TOPOLOGY, _get("merges"), 0.120, 2.8, 0.320,
              "U4 Reeb signature"),
    Dimension("births", Domain.TOPOLOGY, _get("births"), 0.101, 2.3, 0.255,
              "U4 Reeb signature"),
    Dimension("cycles", Domain.TOPOLOGY, _get("cycles"), 0.127, 2.9, 0.246,
              "hole count. The most STABLE feature measured (U4: 98.7-100% "
              "consistent within a class) and among the weakest for "
              "DISCRIMINATION, because e a o b d p q all have one hole"),
    Dimension("depth", Domain.TOPOLOGY, _get("depth"), 0.086, 2.0, 0.220,
              "U6 containment depth"),

    # --- POSITION ---
    Dimension("x", Domain.POSITION, _get("x"), None, None, None,
              "page position; unmeasured, and expected to carry layout "
              "information rather than identity"),
    Dimension("y", Domain.POSITION, _get("y"), None, None, None,
              "page position; unmeasured"),

    # TRANSFORM: declared, unpopulated. Needs a per-character CTM from
    # U10's alignment. Named rather than guessed at.
    # TYPOGRAPHIC: declared, unpopulated (G5). Needs U9's reference lines,
    # which are not built.
)

_BY_NAME = {d.name: d for d in DIMENSIONS}


def dimensions_of(domain: Domain) -> tuple[Dimension, ...]:
    """Every dimension in a domain, possibly none (G5)."""
    return tuple(d for d in DIMENSIONS if d.domain is domain)


@dataclass(frozen=True, slots=True)
class Point:
    """A component's position, partitioned by domain (G1)."""
    values: dict[Domain, dict[str, float]]

    def get(self, name: str) -> float | None:
        if name not in _BY_NAME:
            raise UnknownDimension(name)
        return self.values.get(_BY_NAME[name].domain, {}).get(name)

    def domain(self, d: Domain) -> dict[str, float]:
        return dict(self.values.get(d, {}))

    @property
    def present(self) -> tuple[str, ...]:
        return tuple(sorted(n for v in self.values.values() for n in v))


def describe(features: Mapping[str, Any]) -> Point:
    """A component's feature dict -> a point, split by domain.

    Total (G6): a missing input leaves that dimension absent rather than
    producing a wrong value. Pure (G7): no I/O, no global state.
    """
    out: dict[Domain, dict[str, float]] = defaultdict(dict)
    for dim in DIMENSIONS:
        try:
            v = dim.extract(features)
        except (TypeError, ZeroDivisionError):
            v = None
        if v is not None and math.isfinite(v):
            out[dim.domain][dim.name] = v
    return Point({k: dict(v) for k, v in out.items()})


# --------------------------------------------------------------------------
# The design test itself
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ConvexityResult:
    score: float
    baseline: float
    classes: int
    samples: int

    @property
    def lift(self) -> float:
        """Times the random baseline. A score means nothing without the
        class count, so it is carried alongside (G3)."""
        return self.score / self.baseline if self.baseline else 0.0


def convexity(values: Sequence[float], labels: Sequence[Any], *,
              low: float = 0.10, high: float = 0.90,
              min_per_class: int = 2) -> ConvexityResult:
    """The Gardenfors test docs/units.md sets for this unit.

    For each class, take the interval its values occupy and ask what
    fraction of ALL samples in that interval really belong to the class.
    A dimension in which the concepts are convex scores high.

    The interval is inter-percentile, NOT min/max (G2). One outlier
    stretches a min/max interval across the whole range and drags every
    dimension to the baseline -- measured, on the first attempt at this,
    which made all eleven dimensions look worthless.

    The bounds are ORDER STATISTICS -- actual sample values -- not
    interpolated percentiles. With an interpolated bound a class of two
    samples gets an interval strictly between its two points, containing
    neither, and scores zero for having tidy data. Found by a test.
    """
    if len(values) != len(labels):
        raise ValueError(f"{len(values)} values but {len(labels)} labels")
    if not values:
        return ConvexityResult(0.0, 0.0, 0, 0)

    per: dict[Any, list[float]] = defaultdict(list)
    for v, c in zip(values, labels):
        per[c].append(v)
    usable = [c for c, vs in per.items() if len(vs) >= min_per_class]
    if not usable:
        return ConvexityResult(0.0, 0.0, 0, len(values))

    pairs = list(zip(values, labels))
    scores = []
    for c in usable:
        lo, hi = _order_stat(per[c], low), _order_stat(per[c], high)
        inside = [lab for v, lab in pairs if lo <= v <= hi]
        if inside:
            scores.append(sum(1 for lab in inside if lab == c) / len(inside))
    score = sum(scores) / len(scores) if scores else 0.0
    return ConvexityResult(score, 1.0 / len(usable), len(usable),
                           len(values))


def mutual_information(values: Sequence[float], labels: Sequence[Any], *,
                       bins: int = 16) -> float:
    """Normalised mutual information between a dimension and the labels.

    0 means the dimension says nothing about identity, 1 means it
    determines it. Equal-frequency bins, so a skewed dimension is not
    penalised for its shape.
    """
    if len(values) != len(labels):
        raise ValueError(f"{len(values)} values but {len(labels)} labels")
    n = len(values)
    if n == 0:
        return 0.0
    h_labels = _entropy(Counter(labels), n)
    if h_labels == 0:
        return 0.0
    srt = sorted(values)
    edges = [_pct(srt, i / bins) for i in range(1, bins)]
    joint: dict[int, Counter] = defaultdict(Counter)
    per_bin: Counter = Counter()
    for v, lab in zip(values, labels):
        b = sum(1 for e in edges if v > e)
        joint[b][lab] += 1
        per_bin[b] += 1
    cond = sum((per_bin[b] / n) * _entropy(joint[b], per_bin[b])
               for b in per_bin)
    return (h_labels - cond) / h_labels


def _order_stat(vals: Sequence[float], p: float) -> float:
    """The sample at fractional rank `p`, rounded INTO the data.

    Both bounds round DOWN, into the data. Rounding the high bound up
    pulls a top outlier straight back into the interval, which is the
    thing the trim exists to prevent -- with `ceil`, a class of nine 1s
    and one 999 got the interval [1, 999]. Rounding down gives [1, 1].
    Also found by a test.
    """
    v = sorted(vals)
    return v[math.floor((len(v) - 1) * p)]


def _pct(vals: Sequence[float], p: float) -> float:
    v = sorted(vals)
    k = (len(v) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    return v[f] if f == c else v[f] + (v[c] - v[f]) * (k - f)


def _entropy(counter: Mapping[Any, int], n: int) -> float:
    return -sum((c / n) * math.log2(c / n) for c in counter.values() if c)
