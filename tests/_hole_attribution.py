"""Per-component hole oracle: which component owns how many holes.

Closes the gap left by tests/_hcs2013.py, which checks TOTALS only:
sweep's G3 says cycle_count of EACH component equals ITS holes, and on
random masks that was checked only through the cycle-rank identity, which
lives inside sweep's own graph and cannot refute it.

Method (no runs, no cycle rank, no union-find):
  1. pad the mask with one background pixel all round;
  2. flood-fill ink at 8-connectivity -> component of every ink pixel;
  3. flood-fill background at 4-connectivity; a region that does not
     contain the padding is a hole;
  4. credit each hole to the component of the ink pixel directly LEFT of
     the hole's first pixel in raster order.

Why step 4 names the surrounding component, not an island in the hole:
  the left pixel p is ink (a background left pixel would belong to the
  hole and come earlier). If p belonged to an island I inside the hole,
  the pixel u above I's topmost pixel t is background in the hole, and
  row(u) < row(t) <= row(p) = row(first hole pixel) -- a hole pixel above
  the hole's first row, which is impossible.

Independence: independent of sweep. NOT independent of nest.py, which
uses the same "neighbour of the topmost pixel" parent rule (as does
LSL-BW, Lemaitre & Lacassagne 2020) -- do not use it to check nest.

Contract
  holes_per_component(rows, ink="#") -> {(y, x): holes}
    key   first pixel of the component in raster order (y, then x),
          in unpadded image coordinates
    value number of holes credited to that component (0 included)
  Pure function of `rows`. No I/O.
"""

_N8 = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
_N4 = ((0, -1), (-1, 0), (1, 0), (0, 1))


def holes_per_component(rows, ink="#"):
    rows = list(rows)
    h = len(rows)
    w = len(rows[0]) if h else 0
    W, H = w + 2, h + 2
    fg = [[False] * W for _ in range(H)]
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            fg[y + 1][x + 1] = ch == ink

    def fill(sx, sy, want_fg, nbr, lab, tag):
        stack = [(sx, sy)]
        lab[sy][sx] = tag
        while stack:
            cx, cy = stack.pop()
            for dx, dy in nbr:
                qx, qy = cx + dx, cy + dy
                if (0 <= qx < W and 0 <= qy < H and lab[qy][qx] is None
                        and fg[qy][qx] == want_fg):
                    lab[qy][qx] = tag
                    stack.append((qx, qy))

    comp = [[None] * W for _ in range(H)]
    first = {}                                   # component id -> (y, x)
    n = 0
    for y in range(H):                           # raster order => first pixel
        for x in range(W):
            if fg[y][x] and comp[y][x] is None:
                fill(x, y, True, _N8, comp, n)
                first[n] = (y - 1, x - 1)
                n += 1

    bg = [[None] * W for _ in range(H)]
    fill(0, 0, False, _N4, bg, "outside")        # padding is all one region
    out = {first[c]: 0 for c in range(n)}
    k = 0
    for y in range(H):
        for x in range(W):
            if not fg[y][x] and bg[y][x] is None:
                fill(x, y, False, _N4, bg, k)    # (x, y) is the hole's first pixel
                k += 1
                out[first[comp[y][x - 1]]] += 1
    return out
