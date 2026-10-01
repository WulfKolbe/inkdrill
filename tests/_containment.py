"""Independent containment oracle for `nest.py`'s forest.

WHY A THIRD RULE. `nest` finds a region's parent by ONE LOOKUP: the pixel
directly above the region's topmost-leftmost pixel (its docstring proves
that pixel is always of the opposite kind). `tests/_hole_attribution.py`
credits a hole to the ink pixel directly LEFT of the hole's first pixel
in raster order. Those are the same family -- a neighbour of an extreme
pixel in raster order -- so neither can refute the other, and out/680
recorded that nest was therefore unchecked.

THIS RULE IS CONTAINMENT ITSELF, applied uniformly to ink and background:

  enclosed(R)  flood the COMPLEMENT of R inward from the ring around R's
               bounding box; every pixel the flood cannot reach is
               enclosed by R. Connectivity is paired, so the flood over
               the complement of an 8-connected ink region runs at 4, and
               over the complement of a 4-connected background region at
               8 -- otherwise a 1-px wall leaks.
  parent(X)    the region with the SMALLEST enclosed set among those
               whose enclosed set contains all of X; None when no region
               encloses X (a top-level component, or the outside).

Smallest-enclosing is exactly "innermost", and it is unique: if two
regions both enclose X, one encloses the other, and their enclosed sets
are strictly nested. No raster order, no adjacency, no cycle rank, no
union-find, no run index.

Contract
  forest(rows, ink="#") -> {key: parent_key or None}
    key = (kind, x0, y0, x1, y1, area), kind in {"ink", "hole"}
          -- `nest`'s own Region fields, so the two are comparable
          without either side exposing a pixel.
  Regions touching the image border are background but NOT holes; they
  are dropped, as is the outside. Pure function of `rows`. No I/O.
"""

_N8 = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
_N4 = ((0, -1), (-1, 0), (1, 0), (0, 1))


def _label(grid, h, w, want, neigh):
    """Flood-fill label map for cells equal to `want`; -1 elsewhere."""
    lab = [[-1] * w for _ in range(h)]
    out, n = [], 0
    for sy in range(h):
        for sx in range(w):
            if grid[sy][sx] != want or lab[sy][sx] != -1:
                continue
            stack, pix = [(sy, sx)], []
            lab[sy][sx] = n
            while stack:
                y, x = stack.pop()
                pix.append((y, x))
                for dx, dy in neigh:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and lab[ny][nx] == -1 \
                            and grid[ny][nx] == want:
                        lab[ny][nx] = n
                        stack.append((ny, nx))
            out.append(pix)
            n += 1
    return lab, out


def _enclosed(pix, h, w, neigh):
    """Pixels enclosed by this region: flood its complement inward from
    the ring around its bounding box. `neigh` is the COMPLEMENT's
    connectivity."""
    ys = [y for y, _ in pix]
    xs = [x for _, x in pix]
    y0, y1 = max(0, min(ys) - 1), min(h - 1, max(ys) + 1)
    x0, x1 = max(0, min(xs) - 1), min(w - 1, max(xs) + 1)
    own = set(pix)
    seen = set()
    stack = [(y, x) for y in (y0, y1) for x in range(x0, x1 + 1)]
    stack += [(y, x) for x in (x0, x1) for y in range(y0, y1 + 1)]
    stack = [p for p in stack if p not in own]
    seen.update(stack)
    while stack:
        y, x = stack.pop()
        for dx, dy in neigh:
            ny, nx = y + dy, x + dx
            if y0 <= ny <= y1 and x0 <= nx <= x1 \
                    and (ny, nx) not in seen and (ny, nx) not in own:
                seen.add((ny, nx))
                stack.append((ny, nx))
    return {(y, x) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)
            if (y, x) not in seen and (y, x) not in own}


def _key(kind, pix):
    ys = [y for y, _ in pix]
    xs = [x for _, x in pix]
    return (kind, min(xs), min(ys), max(xs), max(ys), len(pix))


def forest(rows, ink="#"):
    rows = list(rows)
    h = len(rows)
    w = len(rows[0]) if h else 0
    grid = [[1 if (x < len(rows[y]) and rows[y][x] == ink) else 0
             for x in range(w)] for y in range(h)]
    if not h or not w:
        return {}
    ink_lab, ink_pix = _label(grid, h, w, 1, _N8)
    bg_lab, bg_pix = _label(grid, h, w, 0, _N4)

    border = set()
    for i, pix in enumerate(bg_pix):
        if any(y in (0, h - 1) or x in (0, w - 1) for y, x in pix):
            border.add(i)

    regions = []                      # (key, pixels, enclosed)
    for pix in ink_pix:
        regions.append((_key("ink", pix), set(pix), _enclosed(pix, h, w, _N4)))
    for i, pix in enumerate(bg_pix):
        if i in border:
            continue                  # background, but not a hole
        regions.append((_key("hole", pix), set(pix), _enclosed(pix, h, w, _N8)))

    out = {}
    for key, pix, _ in regions:
        best = None
        for okey, opix, oenc in regions:
            if okey == key or not pix <= oenc:
                continue
            if best is None or len(oenc) < best[1]:
                best = (okey, len(oenc))
        out[key] = best[0] if best else None
    return out
