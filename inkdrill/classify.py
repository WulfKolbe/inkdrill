"""classify.py — nearest neighbour over separable channels.

CONTRACT (written before implementation; see docs/units.md U13)
==============================================================

The escalation question, answered before the unit was written
------------------------------------------------------------
docs/units.md sets one instruction: *"escalate beyond nearest neighbour
only after seeing the confusion matrix."* So the confusion matrix was the
premise check. 17,008 real glyph components over 59 classes, half train
half test, majority-class baseline 13.0%:

        signature only              30.7%
        extents only                97.1%
        bitmap only                 99.1%
        bitmap + signature          99.2%
        bitmap + extents            99.3%
        all three                   99.3%

**Do not escalate.** Plain 1-NN on a 12x12 normalised bitmap reaches
99.1%, and every channel added afterwards buys tenths of a point. There
is no confusion-matrix evidence for anything more elaborate, and this
module therefore implements nearest neighbour and nothing else.

What the channels are actually worth
------------------------------------
docs/units.md proposes the bitmap and the Reeb signature as two channels,
with "aspect ratio and absolute extents carried separately (without them
`- - -- ---` and `. *` are unrecoverable)". The measurement adjusts that:

  * **the bitmap channel dominates** -- 99.1% alone;
  * **extents alone reach 97.1%**, which is far more than "carried
    separately" suggests, and matches U12's finding that extents carry
    the most marginal information of any dimension;
  * **the signature is weak alone (30.7%) and adds +0.1pp on top of the
    bitmap.** On clean renders of body text it is close to redundant.

That is not a reason to discard it. U12 measured the topological
dimensions as the most EFFICIENT per available bit and jointly worth
0.713 against a best marginal of 0.375 -- narrow, not weak -- and
`cycles` as 98.7-100% stable within a class. The profile is a VERIFIER:
good for rejecting a wrong answer, poor for generating one. `margin` and
`agrees` exist for that use, rather than the signature being mixed into
one distance and its stability wasted.

Every residual error is structural
----------------------------------
The confusion matrix at 99.3% contains no surprises, only two families:

        ',' -> ';'  x10     ';' -> 'i'  x8      ':' -> '.'  x6
        'i' -> 'l'  x3      'W' -> 'w'  x3      'S' -> 's'  x2
        '1' -> 'i'  x2      'I' -> 'l'  x2      'H' -> 'h'  x1

  * the **punctuation cluster** `, ; : .` -- these are MULTI-COMPONENT
    glyphs, and a per-component classifier sees half of one. U4 and U10
    both hit this; the fix is grouping, not a better classifier.
  * **case pairs** `W/w S/s H/h I/l` that differ only in absolute size.
    This is exactly what `units.md` predicted when it insisted extents be
    carried separately, and it is why `extents` is a channel rather than
    a normalisation.

Neither is fixed by escalating the model.

The bitmap is an integer, deliberately
--------------------------------------
A normalised bitmap is packed into a Python `int`, so Hamming distance is
`(a ^ b).bit_count()` -- one C-speed popcount instead of 144 interpreted
comparisons. This is not micro-optimisation: with per-bit comparison the
premise check above did not finish in 30 minutes, and with popcount it
finished in under five. A classifier nobody can afford to run produces no
confusion matrix, and then the escalation question cannot be answered.

Guarantees
----------
G1  `normalise` is deterministic and size-invariant: the same shape at
    two scales gives the same bits
G2  distance is a metric on each channel -- zero to itself, symmetric,
    non-negative -- so nearest neighbour means what it says
G3  channels are separable and independently usable; the weights are
    explicit arguments, not constants buried in a distance function
G4  every prediction carries its runner-up and the margin between them,
    so a caller can reject rather than being forced to accept
G5  ties break deterministically, by label, so a repeated run gives the
    same answer
G6  classifying against no templates raises rather than inventing a label
G7  `confusion()` reports the offending PAIRS, not only an accuracy --
    the accuracy alone would have hidden that every error is structural

Non-guarantees (out of scope for U13)
-------------------------------------
  * no escalation beyond 1-NN; the confusion matrix does not justify it
  * no grouping of multi-component glyphs. The punctuation cluster needs
    components joined before classification, which is U14's business.
  * no font-rendered reference templates -- that needs U9's rasterizer
    half, which is not built. Templates here come from labelled page ink
    via U10's alignment.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .raster import InkMask

__all__ = ["Template", "Prediction", "Channels", "Classifier",
           "normalise", "bitmap_distance", "signature_distance",
           "extents_distance", "confusion", "NoTemplates"]

GRID = 12


class NoTemplates(ValueError):
    """cannot classify against an empty template set."""


def normalise(mask: InkMask, grid: int = GRID) -> int:
    """A component bitmap resampled to `grid` x `grid`, packed into an int.

    A cell is set when ANY source pixel under it is ink, which keeps thin
    strokes alive at small grid sizes -- the generous rule, so a failure
    is not an artefact of dropping hairlines.

    Returning an `int` rather than bytes is what makes `bitmap_distance`
    a single popcount (see the module docstring).
    """
    w, h = mask.width, mask.height
    if w == 0 or h == 0:
        return 0
    data = mask.data
    v = 0
    bit = 0
    for j in range(grid):
        y0 = j * h // grid
        y1 = max(y0 + 1, (j + 1) * h // grid)
        for i in range(grid):
            x0 = i * w // grid
            x1 = max(x0 + 1, (i + 1) * w // grid)
            hit = False
            for y in range(y0, min(y1, h)):
                row = y * w
                if any(data[row + x] for x in range(x0, min(x1, w))):
                    hit = True
                    break
            if hit:
                v |= 1 << bit
            bit += 1
    return v


def bitmap_distance(a: int, b: int) -> int:
    """Hamming distance, as one popcount."""
    return (a ^ b).bit_count()


def signature_distance(a: Sequence[int], b: Sequence[int]) -> int:
    """L1 over the Reeb signature counts."""
    return sum(abs(x - y) for x, y in zip(a, b))


def extents_distance(a: Sequence[float], b: Sequence[float],
                     *, scale: Sequence[float] = (4.0, 0.025, 0.025, 0.125)
                     ) -> float:
    """Weighted L1 over (aspect, height, width, elongation).

    The scales convert each to comparable units: aspect is O(1) and
    dimensions are O(10-100) pixels, so an unscaled sum would be a pixel
    count with an aspect rounding error attached.
    """
    return sum(abs(x - y) * s for x, y, s in zip(a, b, scale))


@dataclass(frozen=True, slots=True)
class Template:
    """One labelled example. `bitmap` is packed; the other channels are
    the raw feature tuples."""
    label: str
    bitmap: int
    signature: tuple[int, ...] = ()
    extents: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class Channels:
    """Explicit weights (G3). Zero disables a channel, so any single
    channel can be measured alone without a separate code path."""
    bitmap: float = 1.0
    signature: float = 3.0
    extents: float = 6.0

    @property
    def any_enabled(self) -> bool:
        return bool(self.bitmap or self.signature or self.extents)


@dataclass(frozen=True, slots=True)
class Prediction:
    label: str
    distance: float
    runner_up: str | None
    runner_up_distance: float | None

    @property
    def margin(self) -> float:
        """How much better the winner was. A caller rejecting on a small
        margin is the intended use (G4); 0.0 means a tie."""
        if self.runner_up_distance is None:
            return float("inf")
        return self.runner_up_distance - self.distance


@dataclass(slots=True)
class Classifier:
    """Nearest neighbour, and nothing more -- see the module docstring on
    why the confusion matrix does not justify escalating."""
    templates: list[Template] = field(default_factory=list)
    channels: Channels = Channels()

    def add(self, template: Template) -> None:
        self.templates.append(template)

    def distance(self, query: Template, ref: Template) -> float:
        c = self.channels
        d = 0.0
        if c.bitmap:
            d += c.bitmap * bitmap_distance(query.bitmap, ref.bitmap)
        if c.signature and query.signature and ref.signature:
            d += c.signature * signature_distance(query.signature,
                                                  ref.signature)
        if c.extents and query.extents and ref.extents:
            d += c.extents * extents_distance(query.extents, ref.extents)
        return d

    def classify(self, query: Template) -> Prediction:
        """Nearest template, with the runner-up from a DIFFERENT label.

        Ties break by label (G5), so a repeated run gives the same answer
        and a comparison between two runs means something.
        """
        if not self.templates:
            raise NoTemplates("no templates to classify against")
        best: dict[str, float] = {}
        for ref in self.templates:
            d = self.distance(query, ref)
            cur = best.get(ref.label)
            if cur is None or d < cur:
                best[ref.label] = d
        ranked = sorted(best.items(), key=lambda kv: (kv[1], kv[0]))
        label, dist = ranked[0]
        if len(ranked) > 1:
            return Prediction(label, dist, ranked[1][0], ranked[1][1])
        return Prediction(label, dist, None, None)

    def agrees(self, query: Template, label: str) -> bool:
        """Does the SIGNATURE channel alone accept this label?

        The verifier use U12's measurement points at: the signature is
        weak at generating an answer (30.7% alone) and highly stable
        within a class, so it is better asked "is this consistent?" than
        "what is this?".
        """
        if not query.signature:
            return True
        peers = [t for t in self.templates
                 if t.label == label and t.signature]
        if not peers:
            return False
        return any(signature_distance(query.signature, t.signature) == 0
                   for t in peers)


def confusion(classifier: "Classifier",
              queries: Iterable[tuple[str, Template]]
              ) -> tuple[float, Counter]:
    """(accuracy, Counter of (truth, predicted) pairs).

    G7: the pairs, not only the accuracy. At 99.3% the accuracy alone
    would have hidden that every remaining error is either a
    multi-component punctuation glyph or a case pair -- neither of which
    a better model fixes.
    """
    right = 0
    total = 0
    pairs: Counter = Counter()
    for truth, q in queries:
        total += 1
        got = classifier.classify(q).label
        if got == truth:
            right += 1
        else:
            pairs[(truth, got)] += 1
    return (right / total if total else 0.0), pairs
