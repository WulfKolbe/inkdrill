"""Q1: how far a math expression's ink exceeds its declared region.

MathPix declares a region per line. The ink that actually belongs to
a math expression can be LARGER than that box -- a tall fraction, an
integral sign, a matrix that the region clips. The excess fraction
measures it, per expression, in units of the declared region:

    excess = area(ink_bbox) - area(ink_bbox ∩ region)
    fraction = excess / area(region)

0.0 means the ink bbox lies wholly inside the declared region; 1.0
means the ink sticks out by an area equal to the whole region. It is
a RATIO of areas, so it is resolution-free -- the same page at 200
and 400 dpi gives the same number.

Ink is assigned to a region by component CENTRE, the same rule the
compare loop uses, so a neighbouring column cannot lend ink to an
expression it merely touches.

An expression with NO assigned ink yields no measurement (None), not
zero: absence of ink is not evidence of fit, and averaging a zero in
would hide the empty case.
"""

from __future__ import annotations


def _area(x0, y0, x1, y1):
    w = max(0.0, x1 - x0)
    h = max(0.0, y1 - y0)
    return w * h


def excess_fraction(ink, region):
    """(ink bbox, region bbox) -> fraction, both (x0, y0, x1, y1)."""
    ra = _area(*region)
    if ra <= 0:
        return None
    ia = _area(*ink)
    inter = _area(max(ink[0], region[0]), max(ink[1], region[1]),
                  min(ink[2], region[2]), min(ink[3], region[3]))
    return (ia - inter) / ra


def ink_bbox(boxes):
    """Union bbox of the given components, or None when there are none."""
    if not boxes:
        return None
    return (min(b.x0 for b in boxes), min(b.y0 for b in boxes),
            max(b.x1 for b in boxes), max(b.y1 for b in boxes))


def assign(boxes, region, exclude_crossing_rules=True):
    """Components whose CENTRE falls inside the region.

    A RULE-shaped component longer than the region itself is page
    furniture crossing the band -- a table rule, a figure separator --
    not the expression's ink, and it is excluded. Measured: on
    0802.3344 p9 a 795x2 px page rule sat centred in a 391 px region
    and drove the excess fraction to 0.994, which read as the corpus's
    worst under-coverage and was an artifact of attribution. A
    fraction bar, which IS part of an expression, is shorter than the
    region that bounds it and survives the filter.

    `is_rule` is imported rather than re-implemented: one definition
    (fill >= 0.8 and aspect >= 20) for the whole project.
    """
    from inkdrill.emit import is_rule
    x0, y0, x1, y1 = region
    rw, rh = x1 - x0, y1 - y0
    out = []
    for b in boxes:
        if not (x0 <= (b.x0 + b.x1) / 2 <= x1
                and y0 <= (b.y0 + b.y1) / 2 <= y1):
            continue
        if exclude_crossing_rules and is_rule(b) and (
                b.x1 - b.x0 + 1 > rw or b.y1 - b.y0 + 1 > rh):
            continue
        out.append(b)
    return out


def overlaps(math_regions, boxes):
    """[(key, fraction), ...] for every math region that HAS ink."""
    out = []
    for key, region in math_regions:
        bb = ink_bbox(assign(boxes, region))
        if bb is None:
            continue
        f = excess_fraction(bb, region)
        if f is not None:
            out.append((key, f))
    return out
