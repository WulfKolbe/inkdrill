"""classify.py — nearest neighbour over separable channels.

CONTRACT (written before implementation; see docs/units.md U13)
==============================================================

The escalation question, and the split rule that decides it
-----------------------------------------------------------
docs/units.md sets one instruction: *"escalate beyond nearest neighbour
only after seeing the confusion matrix."* So the confusion matrix was the
premise check.

**THE SPLIT RULE IS THE EXPERIMENT.** An earlier revision of this
docstring reported "half train half test" without saying half by what,
and the answer was: by COMPONENT, over pages that appeared on both sides.
Nearly every test glyph had a near-identical twin -- same document, page,
font and size -- in the training half. Measured both ways on the same
8 pages, changing only the split rule:

        channel            by component   by DOCUMENT   by FONT
        signature only         11.8%         11.2%        9.2%
        extents only           93.7%         43.8%       29.5%
        bitmap only            95.7%         94.0%       61.5%
        bitmap + extents       95.8%         95.8%       68.8%
        all three              96.0%         95.7%       86.3%

**The extents channel was almost entirely leakage: 93.7% -> 43.8%.** Its
absolute height and width identify the *document's body size*, not the
character, so with the same document on both sides it is close to a
lookup table. An earlier revision reported 97.1% for extents alone and
drew conclusions from it; that number was an artefact of the protocol.

**The bitmap channel is document-independent but NOT font-independent:
94.0% across documents, 61.5% across fonts.** Normalised shape survives a
change of paper and survives a change of body size; it does not survive a
change of typeface.

**And the channels only earn their keep when the problem is hard.**
Across documents, adding signature and extents to the bitmap buys +1.7
points. Across FONTS it buys **+24.8** -- 61.5% to 86.3%. An earlier
revision concluded from the easy split that "the signature adds nothing
measurable"; that was protocol-dependent too. docs/units.md was right to
specify several channels, and the easy protocol hid why.

So the escalation decision splits by population:

  * **within a document, do not escalate.** 1-NN on the bitmap reaches
    94% and the rest buys under two points.
  * **across fonts, 1-NN is not enough.** 61.5% bitmap-only, 86.3% with
    every channel, and that is the condition for the ~5% of glyphs U9
    found with no usable embedded font and for the entire scanned corpus,
    which has no font to template from at all.

WHAT POPULATION THIS IS MEASURED OVER
-------------------------------------
59 classes survived a "at least 12 instances" filter over 8 body-text
pages. The non-ASCII survivors are `""` and `fi` -- smart quotes and a
ligature. **There is not one mathematics symbol in the measured
population.** No `sum`, `integral`, `radical`, `pm`, `leq`, `in`.

So every number above describes BODY TEXT, and says nothing about the
maths symbols that are this project's first application. Raising the page
count does not fix it: a rare symbol stays rare. Answering it needs pages
selected for maths content, which is not done here. The class filter is
one line and it was a decision, so `measure.py classify` now prints the
surviving class list beside the accuracy table.

What the channels are actually worth
------------------------------------
docs/units.md proposes the bitmap and the Reeb signature as two channels,
with extents "carried separately". Corrected for the split rule:

  * **the bitmap channel carries the within-document case** -- 94% alone;
  * **extents do not generalise across documents alone** (43.8%) but are
    worth +1.8pp on top of the bitmap, which is where the case pairs live;
  * **the signature is weak alone everywhere** (9-12%) and adds nothing
    on the easy splits -- but the three together gain 24.8 points over the
    bitmap alone across fonts, so the channels are complementary exactly
    where a single one fails.

The signature is still exposed as a VERIFIER (`agrees`, `margin`) as well
as a distance term. U12 measured the topological dimensions as narrow but
the most efficient per available bit, and `cycles` as 98.7-100% stable
within a class: good for rejecting a wrong answer, poor for generating
one. Having both uses available is why it is a named channel rather than
a number folded into one distance.

Every residual error is structural
----------------------------------
The confusion matrix at 99.3% contains no surprises, only two families:

        'i' -> '1'  x8      'i' -> '.'  x7      '.' -> 'i'  x3
        'k' -> 'h'  x2      's' -> 'S'  x2      'l' -> 'i'  x1
        ':' -> '.'  x1      'X' -> 'x'  x1

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
G8  every accuracy quoted here names its SPLIT RULE and its population.
    An unqualified accuracy is not a result: the same experiment gives
    43.8% or 93.7% for the extents channel depending on nothing but how
    train and test were divided

Non-guarantees (out of scope for U13)
-------------------------------------
  * no escalation beyond 1-NN; the confusion matrix does not justify it
  * no grouping of multi-component glyphs. The punctuation cluster needs
    components joined before classification, which is U14's business.
  * no font-rendered reference templates -- that needs U9's rasterizer
    half, which is not built. Templates here come from labelled page ink
    via U10's alignment, so the measured protocol is not the deployment
    condition either; it is the closest available.
  * no claim about MATHS SYMBOLS. The measured population is body text --
    see above. This is the project's first application and it is
    unmeasured here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, NamedTuple, Sequence

from .raster import InkMask

__all__ = ["signature_features", "template_of",
           "Template", "Prediction", "Channels", "Classifier",
           "normalise", "bitmap_distance", "signature_distance",
           "extents_distance", "confusion", "confusion_table",
           "ClassRow", "NoTemplates"]

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

    THIS SCANS PIXELS ON PURPOSE, and it is the one place in the package
    where that is right. `algorithms.md` ranked "normalise from the run
    list" as the top remaining improvement at 6.7x; measured, it is a
    PESSIMISATION almost everywhere, because the loop below stops at the
    first ink pixel under a cell. That early exit makes the cost about
    `grid**2` probes whatever the mask's size:

        size       density  runs/area      pixel     run form
        20x20         0.01     0.0100      121us    13us  9.5x
        60x60         0.35     0.2306      125us  1061us  0.12x
        200x200       0.35     0.2270      114us   10.7ms  0.01x
        600x600       0.35     0.2276      132us  100.2ms  0.00x

    The run form wins only where ink is very sparse -- runs/area around
    0.01 -- and real glyph crops measured 1.80x, so they sit near the
    boundary. A run-based rewrite is bit-exact (verified over 4,000
    masks x 5 grid sizes) and up to 800x slower on a textured region,
    which `emit` will hand it whenever a classifier is supplied for a
    figure. Do not re-open this without re-taking that table.
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


def signature_features(sig) -> tuple[int, ...]:
    """A `reeb.Signature` as a feature vector -- ONE definition.

    It was assembled inline at two call sites in the harness and both
    dropped `parts` and `closes`; the second inherited the defect by
    copy and was fixed a commit later than the first. `parts` is exactly
    what separates `i` from `dotlessi` and `Theta` from `O`, so the
    omission made a channel look weak rather than making anything fail.

    It lives here, in the package, because `emit` became a third call
    site and a tuple built at each one drifts.
    """
    return (sig.parts, sig.cycles, sig.births, sig.closes,
            sig.merges, sig.splits)


def template_of(mask: InkMask, label: str) -> "Template | None":
    """A `Template` from one cropped mask -- the query side, and the
    template side, built by the SAME code.

    `None` for an empty mask rather than a zero-feature template, which
    would match anything with no ink.
    """
    from .aggregate import moments_of_mask
    from .reeb import graph_of, signature as reeb_signature
    if mask is None or mask.width == 0 or mask.height == 0:
        return None
    sig = reeb_signature(graph_of(mask))
    mo = moments_of_mask(mask)
    w, h = mask.width, mask.height
    return Template(label, normalise(mask), signature_features(sig),
                    (w / h, float(h), float(w), mo.elongation))


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
    """The RANKED LIST, with the top two as views onto it (C1).

    `classify` always built the full ranking and then threw all but two
    entries away. It is the same information either way -- these are
    properties over `candidates`, not stored fields -- but a consumer
    choosing among labels needs the tail, and the tail is exactly what
    a classifier that must not decide has to hand over.

    `candidates` is `((label, distance), ...)`, ascending by distance
    with ties broken by label (G5), one entry per label.
    """
    candidates: tuple[tuple[str, float], ...]

    def __post_init__(self):
        if not self.candidates:
            raise ValueError(
                "a Prediction needs at least one candidate; `classify` "
                "raises NoTemplates rather than returning an empty one")

    @property
    def label(self) -> str:
        return self.candidates[0][0]

    @property
    def distance(self) -> float:
        return self.candidates[0][1]

    @property
    def runner_up(self) -> str | None:
        return self.candidates[1][0] if len(self.candidates) > 1 else None

    @property
    def runner_up_distance(self) -> float | None:
        return self.candidates[1][1] if len(self.candidates) > 1 else None

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

    def classify(self, query: Template, *, top_k: int = 8) -> Prediction:
        """The nearest `top_k` LABELS, ranked (C1).

        Ties break by label (G5), so a repeated run gives the same answer
        and a comparison between two runs means something.

        `top_k` truncates the report, not the search -- every template
        is still compared, so the first entry is the same one the
        two-field version returned. `top_k=0` means every label.
        """
        if not self.templates:
            raise NoTemplates("no templates to classify against")
        if top_k < 0:
            raise ValueError(f"top_k must be non-negative, got {top_k}")
        best: dict[str, float] = {}
        for ref in self.templates:
            d = self.distance(query, ref)
            cur = best.get(ref.label)
            if cur is None or d < cur:
                best[ref.label] = d
        ranked = sorted(best.items(), key=lambda kv: (kv[1], kv[0]))
        return Prediction(tuple(ranked[:top_k] if top_k else ranked))

    def agrees(self, query: Template, label: str,
               *, extents_tol: float | None = None) -> bool:
        """Is this label CONSISTENT with the query? (verifier, not judge)

        The signature is weak at generating an answer and stable within
        a class, so it is better asked "is this consistent?" than "what
        is this?".

        `extents_tol` makes the check a CONJUNCTION -- signature
        consistent AND extents within tolerance -- and that is not a
        matter of making the verifier finer. A verifier only catches
        errors uncorrelated with its own blind spots. Measured on 647
        maths classes, this same signature-only check caught 1.08% of
        the BITMAP classifier's errors and 44.20% of the EXTENTS
        classifier's: the bitmap picks a wrong label on shape and a
        shape-match usually has matching topology, so the two fail
        together, while extents picks on size and a size-match has
        arbitrary topology, so they fail apart.

        Adding extents covers the one failure the signature cannot see
        by construction: `o` and `O` have the identical signature at
        every size, because it is scale-invariant on purpose.

        Left at None the check is signature-only, which is what every
        recorded figure was measured with.
        """
        if not query.signature:
            return True
        peers = [t for t in self.templates
                 if t.label == label and t.signature]
        if not peers:
            return False
        ok = [t for t in peers
              if signature_distance(query.signature, t.signature) == 0]
        if not ok:
            return False
        if extents_tol is None:
            return True
        if not query.extents:
            return True
        return any(t.extents and
                   extents_distance(query.extents, t.extents) <= extents_tol
                   for t in ok)

    def prune(self, query: Template, candidates,
              *, extents_tol: float | None = None, sig_tol: int = 0):
        """`agrees` over a LIST: the candidates consistent with `query`.

        Same test, applied to every candidate instead of to one. The
        accept/reject form answered "is the winner consistent?", which
        throws away the thing a consumer needs -- HOW MANY survive. A
        pruner that leaves five candidates has done most of the work; one
        that leaves four hundred has done none, and the old signature
        could not tell those apart.

        `candidates` is a `Prediction.candidates`-shaped sequence, and
        the return keeps its order and its distances, so pruning
        composes with ranking rather than replacing it.

        AN EMPTY RESULT IS A LEGITIMATE VALUE. It says every candidate
        is inconsistent with the ink, which is a finding -- the residual
        this project exists to report -- and not an error to be papered
        over by returning the unpruned list.
        """
        if not query.signature:
            return tuple(candidates)
        # One pass over the templates rather than one per candidate:
        # `agrees` scans `self.templates` each call, which is fine for
        # the single-label question it was written for and quadratic
        # over a 647-class candidate list.
        peers: dict[str, list] = {}
        for t in self.templates:
            if t.signature:
                peers.setdefault(t.label, []).append(t)
        out = []
        for lab, dist in candidates:
            ok = [t for t in peers.get(lab, ())
                  if signature_distance(query.signature,
                                        t.signature) <= sig_tol]
            if not ok:
                continue
            if extents_tol is None or not query.extents:
                out.append((lab, dist))
            elif any(t.extents and extents_distance(query.extents, t.extents)
                     <= extents_tol for t in ok):
                out.append((lab, dist))
        return tuple(out)


class ClassRow(NamedTuple):
    """One class's row of a confusion table."""
    support: int
    correct: int
    recall: float


def confusion_table(pairs: Iterable[tuple[str, str]]
                    ) -> tuple[dict[str, ClassRow], Counter]:
    """Per-class (support, correct, recall) and the off-diagonal pairs.

    `pairs` is EVERY classification as `(truth, predicted)`, correct
    ones included -- unlike `confusion`, whose Counter holds only the
    errors and therefore cannot tell how many chances a class had.
    `confusion` is unchanged; this is a second reading of the same
    data, not a replacement.

    WHY A PER-CLASS TABLE AND NOT AN ACCURACY. A single accuracy is a
    MICRO average: it weights each query equally, so a class holding
    90% of the population sets it almost alone. Macro recall weights
    each CLASS equally. The two answer different questions and can be
    far apart:

        micro = sum(r.correct for r in table.values()) \
                / sum(r.support for r in table.values())
        macro = mean(r.recall for r in table.values())

    On a 90/5/5 population where the large class is perfect and the
    two small ones are never right, micro is 0.90 and macro is 0.33.
    Quoting the first as "accuracy" says the classifier works; the
    second says two of its three classes do not exist as far as it is
    concerned. This project's standing rule -- state the population
    beside the number -- has a sharper form here: state which AVERAGE,
    because the population is inside the average.

    Classes appear by TRUTH. A label that was only ever predicted, and
    never true, has no support and no recall, so it is absent from the
    table and present in the off-diagonal Counter -- which is where a
    reader should look for it, not at a row of zeroes implying it was
    tested.
    """
    support: Counter = Counter()
    correct: Counter = Counter()
    off: Counter = Counter()
    for truth, got in pairs:
        support[truth] += 1
        if got == truth:
            correct[truth] += 1
        else:
            off[(truth, got)] += 1
    return ({lab: ClassRow(support[lab], correct[lab],
                           correct[lab] / support[lab])
             for lab in support}, off)


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
