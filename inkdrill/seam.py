"""seam.py -- a minimum-ink path down a page, for CURVED gutters.

CONTRACT (written before implementation; see docs/units.md A3)
=============================================================

Scope, and why it is narrow
---------------------------
**A flat gutter does not need this.** `measure.py white` recovers a
two-column gutter as a single white blob -- 8.1 pt x 601 pt, exactly --
with no dynamic programming at all, because on a flat page the gutter is
a straight run of background and the white-run analysis already finds
straight runs of background.

A seam earns its place only where the gutter is **curved**: a scanned
book spine, a photographed page, anything where the column boundary
bends and no straight stripe fits inside it. Reaching for this on a flat
page is slower and no better, and that is recorded here so it is not
re-derived.

Cost, and why the grid is coarse
--------------------------------
A pure-Python pass over a real page -- 3307 x 4677 is 15.5M cells, each
scanning `2*budget+1` predecessors -- extrapolates to about **17 seconds
per seam**, and a table needs one per gutter. It is not viable at pixel
resolution.

It does not need to be. A gutter is tens of pixels wide, so the seam's
precision requirement is "between two columns", not "to the pixel". The
cost grid is therefore **blocks of ink counts** -- at 8x8 a real page is
240k cells, roughly 0.3 s -- and the path is returned at block
resolution with an explicit `block` so a caller can refine near it if it
ever needs to.

The convergence property
------------------------
**`budget=0` must reduce to the rigid stripe**: with no lateral freedom
the seam is a straight vertical line, and it must be the straight line
of least ink. That is the check that the dynamic programme is solving
the problem it claims to -- a wrong recurrence still returns a path, and
only the degenerate case exposes it. It is the same shape of property as
`band.stitch` being indistinguishable from one sweep at any K.

Guarantees
----------
G1  pure -- a mask in, a path out; nothing is modified and no file read
G2  `budget=0` returns a straight vertical line, at the column of least
    ink, identical to what a rigid-stripe scan would choose
G3  the path is contiguous under the budget: `|x[i+1] - x[i]| <= budget`
    for every step, so it can never jump a column
G4  the path spans every row of the cost grid -- one x per row, no gaps
G5  a path is returned for any non-empty mask, including one that is
    entirely ink; a page with no clear gutter has a least-bad seam and
    the caller decides whether its cost is acceptable
G6  `cost` is returned beside the path, because a seam with no gutter to
    find still returns a path and the cost is the only thing that says so
"""

from __future__ import annotations

from dataclasses import dataclass

from .raster import InkMask

__all__ = ["Seam", "cost_grid", "find_seam", "approximate_line",
           "is_horizontal_line", "is_border_line", "resample_line"]


@dataclass(frozen=True, slots=True)
class Seam:
    """A path down the page, at block resolution.

    `xs[i]` is the block column chosen for block row `i`. Multiply by
    `block` for pixels; the block size travels with the path so a caller
    cannot mix resolutions by accident.
    """
    xs: tuple[int, ...]
    cost: int
    block: int

    def pixel_xs(self) -> tuple[int, ...]:
        """Path in pixels, at the centre of each block."""
        half = self.block // 2
        return tuple(x * self.block + half for x in self.xs)


def cost_grid(mask: InkMask, block: int = 8):
    """Ink counts per `block` x `block` cell -- the seam's input.

    Summed from the mask directly. A cell's cost is how much ink a seam
    crossing it would cut through.
    """
    if block <= 0:
        raise ValueError(f"block must be positive, got {block}")
    w, h = mask.width, mask.height
    gw = (w + block - 1) // block
    gh = (h + block - 1) // block
    grid = [[0] * gw for _ in range(gh)]
    data = mask.data
    for y in range(h):
        row = grid[y // block]
        base = y * w
        # `bytes.find` skips background at C speed, so only inked spans
        # are visited rather than every pixel.
        pos = data.find(b"\xff", base, base + w)
        while pos >= 0:
            end = data.find(b"\x00", pos, base + w)
            if end < 0:
                end = base + w
            for p in range(pos, end):
                row[(p - base) // block] += 1
            pos = data.find(b"\xff", end, base + w)
    return grid, gw, gh


def find_seam(mask: InkMask, *, budget: int = 1, block: int = 8) -> Seam:
    """The least-ink path from top to bottom (G1-G6).

    `budget` is the lateral freedom per block row, in blocks. Zero gives
    the straight line of least ink (G2); one lets the seam follow a
    gentle curve; larger values follow a sharper one at the cost of
    admitting paths a gutter would not take.
    """
    if budget < 0:
        raise ValueError(f"budget must be non-negative, got {budget}")
    grid, gw, gh = cost_grid(mask, block)
    if gw == 0 or gh == 0:
        return Seam((), 0, block)

    # Rows accumulate; `back` remembers the predecessor so the path can
    # be walked out rather than recomputed.
    acc = list(grid[0])
    back = [[0] * gw for _ in range(gh)]
    for y in range(1, gh):
        prev, row, nxt = acc, grid[y], [0] * gw
        bay = back[y]
        for x in range(gw):
            lo = x - budget if x - budget > 0 else 0
            hi = x + budget + 1 if x + budget + 1 < gw else gw
            best = lo
            bestv = prev[lo]
            for k in range(lo + 1, hi):
                if prev[k] < bestv:
                    bestv = prev[k]
                    best = k
            nxt[x] = row[x] + bestv
            bay[x] = best
        acc = nxt

    end = min(range(gw), key=lambda x: (acc[x], x))     # ties: leftmost
    xs = [0] * gh
    xs[gh - 1] = end
    for y in range(gh - 1, 0, -1):
        xs[y - 1] = back[y][xs[y]]
    return Seam(tuple(xs), acc[end], block)


# --------------------------------------------------------------------------
# line helpers -- small, and shared with the warp work
# --------------------------------------------------------------------------

def approximate_line(points):
    """Least-squares fit of `points` as `(x0, y0, x1, y1)`.

    Fits whichever axis spans further, so a near-vertical line is fitted
    x-on-y rather than y-on-x -- the other way round the slope diverges.
    """
    pts = list(points)
    if len(pts) < 2:
        raise ValueError("a line needs at least two points")
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(pts)
    if max(xs) - min(xs) >= max(ys) - min(ys):
        a, b = xs, ys
        flip = False
    else:
        a, b = ys, xs
        flip = True
    ma = sum(a) / n
    mb = sum(b) / n
    den = sum((v - ma) ** 2 for v in a)
    slope = 0.0 if den == 0 else sum((a[i] - ma) * (b[i] - mb)
                                     for i in range(n)) / den
    lo, hi = min(a), max(a)
    p0 = (lo, mb + slope * (lo - ma))
    p1 = (hi, mb + slope * (hi - ma))
    if flip:
        p0, p1 = (p0[1], p0[0]), (p1[1], p1[0])
    return (p0[0], p0[1], p1[0], p1[1])


def is_horizontal_line(line) -> bool:
    """Wider than tall. Ties count as horizontal, so a single point or a
    perfect diagonal has one answer rather than two."""
    x0, y0, x1, y1 = line
    return abs(x1 - x0) >= abs(y1 - y0)


def is_border_line(line, width: int, height: int, *,
                   margin: float = 0.025) -> bool:
    """Within `margin` of a page edge, as a fraction of the page.

    The same rule as the ink-bounded white-run filter, arrived at from
    the other direction: a line at the edge is the page boundary rather
    than content, exactly as a white run touching the edge is a margin
    rather than a gap.
    """
    x0, y0, x1, y1 = line
    mx, my = width * margin, height * margin
    return (min(x0, x1) <= mx or max(x0, x1) >= width - mx
            or min(y0, y1) <= my or max(y0, y1) >= height - my)


def resample_line(points, count: int):
    """`count` points spaced evenly along the polyline by ARC LENGTH.

    Even spacing in arc length, not in index: a polyline with a long
    segment and a short one would otherwise be sampled densely on the
    short one, which is where two line sets stop being comparable.
    """
    pts = list(points)
    if count < 2:
        raise ValueError("resampling needs at least two points")
    if len(pts) < 2:
        raise ValueError("a polyline needs at least two points")
    seg = []
    total = 0.0
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        d = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        seg.append(d)
        total += d
    if total == 0.0:
        return [pts[0]] * count
    out = []
    step = total / (count - 1)
    i = 0
    walked = 0.0
    for k in range(count):
        target = step * k
        while i < len(seg) - 1 and walked + seg[i] < target:
            walked += seg[i]
            i += 1
        t = 0.0 if seg[i] == 0 else (target - walked) / seg[i]
        t = max(0.0, min(1.0, t))
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        out.append((ax + t * (bx - ax), ay + t * (by - ay)))
    return out
