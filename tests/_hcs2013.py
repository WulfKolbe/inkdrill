"""Independent oracle for sweep's component and hole counts.

Source: He, Chao, Suzuki, "An Algorithm for Connected-Component Labeling,
Hole Labeling and Euler Number Computing", J. Comput. Sci. Technol. 28(3),
2013, 468-478 (Sections 2.1 and 3.1). Foreground first scan as in He, Chao,
Suzuki, Wu, Pattern Recognition 42 (2009), Section 3.

It shares no code and no method with sweep: pixel masks, a representative
table with linked equivalent-label sets, no runs, no cycle rank.

Contract
  count(rows, ink="#") -> (ncc, nh)
    ncc  number of 8-connected ink components
    nh   number of 4-connected background components that do not touch
         the image border (holes)
  Pure function of `rows` (list of equal-length strings). No I/O.

Two deliberate departures from the paper, both measured (see out/680.txt):
  D1  The image is padded with background (1 left/top/bottom, 2 right).
      The paper ASSUMES border pixels are background and gives label 0 to
      border-connected background; padding makes the assumption true.
  D2  The hole label range is N*M/2, not the paper's N*M/4. Under the hole
      mask of Fig.5 a background pixel with ink left and above takes a new
      label, so a checkerboard needs ~N*M/2 hole labels; with N*M/4 they
      overflow into the foreground range and the counts are wrong.
      Foreground labels are bounded by ceil(N/2)*ceil(M/2).
"""


def count(rows, ink="#"):
    rows = list(rows)
    h = len(rows)
    w = len(rows[0]) if h else 0
    pw, ph = w + 3, h + 2
    H = pw * ph // 2 + 1                        # D2: hole labels 0..H
    size = H + 1 + ((pw + 1) // 2) * ((ph + 1) // 2) + 1
    R = [0] * size
    NX = [-1] * size
    LS = [0] * size

    def mkset(l):
        R[l] = l
        NX[l] = -1
        LS[l] = l

    def combine(u, v):                          # Sec. 2.1, on representatives
        if u < v:
            k = v
            while k != -1:
                R[k] = u
                k = NX[k]
            NX[LS[u]] = v
            LS[u] = LS[v]
        elif u > v:
            k = u
            while k != -1:
                R[k] = v
                k = NX[k]
            NX[LS[v]] = u
            LS[v] = LS[u]

    b = [[0] * pw for _ in range(ph)]           # D1: padding is label 0
    mkset(0)
    l, lh = H + 1, 1
    for y in range(1, ph):
        row = rows[y - 1] if y - 1 < h else ""
        by, bu = b[y], b[y - 1]
        for x in range(1, pw - 1):
            fg = (y - 1 < h and x - 1 < w and row[x - 1] == ink)
            if fg:
                c1, c2, c3, c4 = by[x - 1], bu[x - 1], bu[x], bu[x + 1]
                if c3 > H:
                    by[x] = c3
                elif c1 > H:
                    by[x] = c1
                    if c4 > H:
                        combine(R[c1], R[c4])
                elif c2 > H:
                    by[x] = c2
                    if c4 > H:
                        combine(R[c2], R[c4])
                elif c4 > H:
                    by[x] = c4
                else:
                    mkset(l)
                    by[x] = l
                    l += 1
            else:
                left, up = by[x - 1], bu[x]
                if left > H:                     # Fig.5(b)
                    if up <= H:
                        by[x] = up
                    else:
                        mkset(lh)
                        by[x] = lh
                        lh += 1
                else:                            # Fig.5(c)
                    by[x] = left
                    if up <= H:
                        combine(R[left], R[up])
    ncc = sum(1 for i in range(H + 1, l) if R[i] == i)
    nh = sum(1 for i in range(1, lh) if R[i] == i)
    return ncc, nh
