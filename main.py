"""Paint Orivane and encode it as a truecolor PNG using only the stdlib."""

from math import ceil, floor, hypot, sin
from pathlib import Path
from random import Random
from struct import pack
from zlib import compress, crc32


WIDTH, HEIGHT = 800, 1000
CREAM = (245, 234, 212)
MIST = (140, 181, 190)
FOREST = (21, 79, 67)
STONE = (222, 164, 93)
CLAY = (201, 107, 75)


def mix(first, second, ratio):
    return tuple(round(a + (b - a) * ratio) for a, b in zip(first, second))


def clamp(value, low=0, high=1):
    return min(high, max(low, value))


def curve(start, *segments):
    """Flatten joined cubic Béziers at a density proportional to their length."""
    points = [start]
    for a, b, end in segments:
        length = hypot(a[0] - start[0], a[1] - start[1])
        length += hypot(b[0] - a[0], b[1] - a[1])
        length += hypot(end[0] - b[0], end[1] - b[1])
        steps = max(5, ceil(length / 7))
        for i in range(1, steps + 1):
            t = i / steps
            s = 1 - t
            weights = (s**3, 3*s*s*t, 3*s*t*t, t**3)
            points.append(tuple(
                sum(w * p[axis] for w, p in zip(weights, (start, a, b, end)))
                for axis in (0, 1)
            ))
        start = end
    return points


class Painter:
    def __init__(self):
        self.rgb = bytearray(WIDTH * HEIGHT * 3)

    def blend(self, x, y, color, alpha):
        if 0 <= x < WIDTH and 0 <= y < HEIGHT and alpha > 0:
            i = (y * WIDTH + x) * 3
            for channel, ink in enumerate(color):
                paper = self.rgb[i + channel]
                self.rgb[i + channel] = round(paper + (ink - paper) * alpha)

    def span(self, left, right, y, color, opacity=1):
        left, right = max(0, left), min(WIDTH, right)
        if right <= left:
            return
        lo, hi = ceil(left), floor(right)
        if lo > hi:
            self.blend(floor(left), y, color, (right-left)*opacity)
            return
        if lo < hi and opacity == 1:
            offset = y * WIDTH * 3
            self.rgb[offset+lo*3:offset+hi*3] = bytes(color) * (hi-lo)
        else:
            for x in range(lo, hi):
                self.blend(x, y, color, opacity)
        self.blend(lo-1, y, color, (lo-left)*opacity)
        self.blend(hi, y, color, (right-hi)*opacity)

    def polygon(self, points, color):
        """Scan-convert with four vertical samples and fractional edge coverage."""
        rows = {}
        for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
            if y1 < y0:
                x0, y0, x1, y1 = x1, y1, x0, y0
            if y1 == y0:
                continue
            slope = (x1-x0)/(y1-y0)
            for sub in range(max(0, ceil(4*y0-.5)), min(4*HEIGHT, ceil(4*y1-.5))):
                rows.setdefault(sub, []).append(x0 + ((sub+.5)/4-y0)*slope)
        for y in sorted({sub//4 for sub in rows}):
            spans = []
            for sub in range(4*y, 4*y+4):
                crossings = sorted(rows.get(sub, ()))
                spans.extend(zip(crossings[::2], crossings[1::2]))
            # Fill opaque interiors in one write. Sum coverage only at boundaries.
            if len(spans) == 4 and max(a for a, _ in spans) < min(b for _, b in spans):
                lo = ceil(max(a for a, _ in spans))
                hi = floor(min(b for _, b in spans))
            else:
                lo = hi = 0
            if hi > lo:
                self.span(lo, hi, y, color)
                spans = [(a, lo) for a, _ in spans] + [(hi, b) for _, b in spans]
            coverage = {}
            for a, b in spans:
                a, b = max(0, a), min(WIDTH, b)
                for x in range(floor(a), ceil(b)):
                    part = min(b, x+1) - max(a, x)
                    coverage[x] = coverage.get(x, 0) + part*.25
            for x, alpha in coverage.items():
                self.blend(x, y, color, min(1, alpha))

    def ellipse(self, x, y, rx, ry, color, opacity=1):
        for row in range(max(0, floor(y-ry)), min(HEIGHT, ceil(y+ry))):
            spans = []
            for sub in (.125, .375, .625, .875):
                t = (row + sub - y) / ry
                if abs(t) < 1:
                    r = rx * (1-t*t)**.5
                    spans.append(r)
            if spans:
                self.span(x-sum(spans)/len(spans), x+sum(spans)/len(spans),
                          row, color, opacity*len(spans)/4)

    def stroke(self, points, width, color):
        frames = normals(points)
        r = width/2
        left = [(x+r*nx, y+r*ny) for (x, y), (nx, ny) in zip(points, frames)]
        right = [(x-r*nx, y-r*ny) for (x, y), (nx, ny) in zip(points, frames)]
        self.polygon(left + right[::-1], color)
        for x, y in (points[0], points[-1]):
            self.ellipse(x, y, r, r, color)


def normals(points):
    result = []
    for i in range(len(points)):
        x0, y0 = points[max(0, i-1)]
        x1, y1 = points[min(len(points)-1, i+1)]
        dx, dy = x1-x0, y1-y0
        length = hypot(dx, dy)
        result.append((dy/length, -dx/length))
    return result


# Solid stems, clipped corners, and intentionally wide counters.
FONT = {
    "O": ("..#####..", ".#######.", "###...###", "##.....##", "##.....##",
          "##.....##", "##.....##", "##.....##", "###...###", ".#######.", "..#####.."),
    "R": ("#######..", "########.", "##....###", "##.....##", "##....###",
          "########.", "#######..", "##...###.", "##....###", "##.....##", "##.....##"),
    "I": ("#####", "#####", ".###.", ".###.", ".###.", ".###.",
          ".###.", ".###.", ".###.", "#####", "#####"),
    "V": ("##.....##", "##.....##", "##.....##", ".##...##.", ".##...##.",
          "..##.##..", "..##.##..", "..#####..", "...###...", "...###...", "....#...."),
    "A": ("...###...", "...###...", "..#####..", "..##.##..", ".###.###.",
          ".##...##.", ".#######.", "#########", "##.....##", "##.....##", "##.....##"),
    "N": ("##.....##", "###....##", "####...##", "####...##", "##.##..##",
          "##..##.##", "##..##.##", "##...####", "##...####", "##....###", "##.....##"),
    "E": ("########", "########", "##......", "##......", "##......",
          "#######.", "#######.", "##......", "##......", "########", "########"),
}


def title(paint):
    word = "ORIVANE"
    scale_x, scale_y, tracking = 9, 8, 15
    width = sum(len(FONT[letter][0])*scale_x for letter in word)
    width += (len(word)-1)*tracking
    left = (WIDTH-width)//2
    for letter in word:
        for j, row in enumerate(FONT[letter]):
            for i, pixel in enumerate(row):
                if pixel == "#":
                    x, y = left+i*scale_x, 62+j*scale_y
                    for scan in range(y, y+scale_y):
                        paint.span(x, x+scale_x, scan, FOREST)
        left += len(FONT[letter][0])*scale_x + tracking


def backdrop(paint):
    for y in range(HEIGHT):
        shade = mix(CREAM, MIST, clamp(y/630)**1.27)
        paint.span(0, WIDTH, y, shade)

    # Long wisps occupy the shoulders of the poster and leave the title clear.
    for x, y, w, h, color in (
        (-48, 225, 310, 25, (236, 230, 208)),
        (523, 209, 312, 18, (232, 228, 209)),
        (590, 286, 251, 15, (222, 224, 204)),
        (-65, 408, 255, 14, (204, 216, 200)),
    ):
        wisp = curve((x, y+h),
                     ((x+w*.19, y+h), (x+w*.29, y-h*.45), (x+w*.55, y+h*.36)),
                     ((x+w*.67, y+h*.67), (x+w*.78, y+h*.64), (x+w, y+h*.85)),
                     ((x+w*.81, y+h*1.21), (x+w*.23, y+h*1.34), (x, y+h)))
        paint.polygon(wisp, color)

    hills = [
        ((-10, 550), ((125, 467), (171, 501), (284, 552)),
         ((452, 620), (608, 476), (810, 506)), (156, 186, 180)),
        ((-10, 582), ((143, 588), (200, 540), (298, 548)),
         ((467, 537), (509, 618), (810, 553)), (130, 169, 161)),
        ((-10, 566), ((119, 536), (247, 639), (379, 605)),
         ((515, 563), (635, 543), (810, 591)), (112, 151, 140)),
        ((-10, 613), ((159, 581), (281, 631), (419, 621)),
         ((550, 610), (663, 588), (810, 600)), (155, 166, 126)),
        ((-10, 624), ((128, 600), (266, 639), (411, 631)),
         ((560, 618), (698, 615), (810, 618)), (136, 154, 109)),
    ]
    for start, a, b, color in hills:
        paint.polygon(curve(start, a, b) + [(810, HEIGHT), (-10, HEIGHT)], color)

    for start, a, b, color in (
        ((-10, 687), ((159, 630), (290, 671), (409, 653)),
         ((563, 627), (691, 657), (810, 643)), (158, 164, 106)),
        ((-10, 780), ((202, 685), (298, 741), (489, 704)),
         ((619, 679), (738, 682), (810, 699)), (166, 167, 107)),
        ((-10, 896), ((140, 792), (345, 837), (520, 783)),
         ((626, 744), (716, 737), (810, 761)), (149, 156, 93)),
        ((-10, 964), ((185, 896), (358, 886), (495, 829)),
         ((633, 779), (743, 788), (810, 815)), (138, 147, 87)),
    ):
        paint.polygon(curve(start, a, b) + [(810, HEIGHT), (-10, HEIGHT)], color)


def rock_loop(paint):
    meadow = paint.rgb[652*WIDTH*3:790*WIDTH*3]
    spine = curve(
        (122, 726),
        ((212, 644), (254, 564), (229, 490)),
        ((221, 448), (188, 418), (191, 367)),
        ((198, 284), (283, 229), (384, 231)),
        ((508, 228), (609, 291), (613, 394)),
        ((619, 493), (514, 528), (498, 588)),
        ((485, 635), (529, 659), (606, 739)),
    )
    distance = [0]
    for (x, y), (a, b) in zip(spine, spine[1:]):
        distance.append(distance[-1]+hypot(a-x, b-y))
    frames = normals(spine)

    def edge(level):
        points = []
        for (x, y), (nx, ny), length in zip(spine, frames, distance):
            t = length/distance[-1]
            root = max(0, 1-t/.125, (t-.89)/.11)
            thickness = 31 + 8*sin(5*t) + 22*root + 3*sin(20*t)
            offset = thickness*level + 2.3*sin(29*t+level) + 1.3*sin(74*t)
            points.append((x+nx*offset, y+ny*offset))
        return points

    # Each band is a closed thick stroke. Small variations follow the bedding.
    outside = edge(1)
    for level, color in (
        (-1.00, (161, 79, 57)),
        (-.88, (181, 87, 61)),
        (-.71, CLAY),
        (-.56, (208, 123, 78)),
        (-.43, (218, 145, 86)),
        (-.20, STONE),
        ( .22, (231, 176, 105)),
        ( .60, (239, 191, 121)),
        ( .86, (246, 207, 141)),
    ):
        paint.polygon(outside + edge(level)[::-1], color)

    for level, begin, end, width, color in (
        (-.80, .15, .69, 1.3, (199, 113, 77)),
        (-.67, .05, .33, 2.3, (189, 92, 62)),
        (-.36, .28, .79, 1.7, (237, 162, 102)),
        (-.04, .09, .43, 2.8, (206, 138, 80)),
        ( .10, .60, .95, 2.2, (214, 144, 81)),
        ( .38, .18, .57, 1.8, (245, 198, 127)),
        ( .73, .34, .72, 1.3, (251, 213, 148)),
        ( .53, .75, .96, 1.5, (239, 186, 114)),
    ):
        line = [point for point, length in zip(edge(level), distance)
                if begin < length/distance[-1] < end]
        paint.stroke(line, width, color)

    # The rock extends behind the meadow. Reveal the original grass along a
    # shallow, irregular rise at each foot, then put broken bedding at its toe.
    for x in range(WIDTH):
        if x < 350:
            grade = 673 + .079*(x-173) + 2.4*sin(x/16) + .8*sin(x/5)
        else:
            grade = 682 + .057*(x-548) + 2.1*sin(x/17) + .7*sin(x/5)
        for y in range(floor(grade), 790):
            index = (y*WIDTH+x)*3
            meadow_index = ((y-652)*WIDTH+x)*3
            paint.blend(x, y, meadow[meadow_index:meadow_index+3], clamp(y+1-grade))
    for x, y, w, h in (
        (116, 674, 23, 7), (145, 681, 15, 5), (193, 675, 26, 9),
        (222, 677, 12, 4), (477, 680, 14, 5), (506, 681, 22, 8),
        (564, 687, 19, 6), (591, 692, 13, 5),
    ):
        paint.ellipse(x+w*.32, y+1, w*.67, h*.36, (102, 111, 75), .55)
        paint.polygon([(x-w*.55, y), (x-w*.25, y-h*.71), (x+w*.13, y-h),
                       (x+w*.55, y-h*.26), (x+w*.42, y)], (182, 126, 79))
        paint.polygon([(x-w*.55, y), (x-w*.25, y-h*.71), (x+w*.13, y-h),
                       (x+w*.32, y-h*.59), (x-w*.16, y-h*.27)], (212, 162, 101))


def lane():
    center = curve(
        (401, 620),
        ((376, 637), (355, 662), (393, 702)),
        ((431, 742), (531, 751), (513, 810)),
        ((499, 852), (350, 901), (314, 1004)),
    )
    result = {}
    for (x, y), (a, b) in zip(center, center[1:]):
        for row in range(ceil(y), ceil(b)):
            t = (row-620)/380
            result[row] = (x+(a-x)*(row-y)/(b-y), 2.5+87*t**1.68)
    return result


def promenade(paint, road):
    steps = list(range(620, 1004, 3)) + [1003]

    def rim(rows, side, extra=0):
        return [(road[y][0] + side*(road[y][1]+extra), y) for y in rows]

    paint.polygon(rim(steps, -1, 4) + rim(steps, 1, 4)[::-1], (178, 157, 99))
    paint.polygon(rim(steps, -1) + rim(steps, 1)[::-1], (230, 209, 158))
    paint.polygon(rim(steps, -1) + [
        (road[y][0] - road[y][1]*.63, y) for y in reversed(steps)
    ], (243, 223, 176))

    # A reflected red-violet shade lies across the warm gravel.
    for y in range(650, 765):
        center, width = road[y]
        for x in range(floor(center-width), ceil(center+width)):
            shadow_center = 683 + .26*(x-365)
            half_band = 21 + .023*(x-360)
            shade = clamp((half_band-abs(y-shadow_center))/10)
            shade *= clamp(min(x+1-(center-width), center+width-x))
            if shade:
                paint.blend(x, y, (133, 118, 104), .58*shade)


def grove_floor(paint):
    # Furrows converge toward two points on either side of the promenade.
    for pivot, destinations in ((320, (-552, -370, -196, -21, 142)),
                                (430, (530, 689, 856, 1028, 1200))):
        for index, end in enumerate(destinations):
            t = index*.7
            ridge = curve(
                (pivot+(end-pivot)*.055, 643),
                ((pivot+(end-pivot)*.21, 707), (pivot+(end-pivot)*.57, 852), (end, 1012)),
            )
            paint.polygon([(x-(y-620)*.084, y) for x, y in ridge] +
                          [(x+(y-620)*.021, y) for x, y in reversed(ridge)],
                          (122+round(t), 138+round(t), 83))
            paint.polygon([(x-(y-620)*.089, y) for x, y in ridge] +
                          [(x-(y-620)*.074, y) for x, y in reversed(ridge)],
                          (174, 172, 109))
    for x, y, rx, ry, alpha in (
        (444, 680, 176, 17, .19), (477, 690, 165, 13, .17),
        (528, 705, 148, 15, .13), (554, 717, 128, 11, .12),
    ):
        paint.ellipse(x, y, rx, ry, (63, 80, 62), alpha)


def cottage(paint, x, y, s):
    def shape(points, color):
        paint.polygon([(x+a*s, y+b*s) for a, b in points], color)

    paint.ellipse(x+8*s, y+1*s, 30*s, 6*s, (89, 108, 76), .42)
    shape([(-22, 0), (7, 0), (7, -22), (-22, -22)], (242, 222, 179))
    shape([(7, 0), (22, -5), (22, -26), (7, -22)], (209, 185, 142))
    shape([(-27, -20), (-18, -34), (12, -34), (9, -20)], (190, 94, 62))
    shape([(9, -20), (12, -34), (26, -25), (22, -21)], (144, 72, 56))
    shape([(-17, -30), (11, -30), (12, -32), (-16, -32)], (218, 126, 78))
    shape([(-5, 0), (2, 0), (2, -13), (-5, -13)], (118, 91, 68))
    shape([(-17, -8), (-11, -8), (-11, -15), (-17, -15)], (94, 116, 98))
    shape([(12, -9), (17, -11), (17, -16), (12, -14)], (114, 119, 92))


def tree(paint, x, y, r, variant, rng):
    deep = mix(FOREST, (37, 74, 62), variant)
    mid = mix((62, 113, 74), (89, 125, 74), variant)
    sun = mix((110, 142, 77), (145, 156, 84), variant)
    paint.ellipse(x+.83*r, y+.08*r, 1.35*r, .23*r, (52, 83, 63), .35)
    paint.ellipse(x+.35*r, y, .65*r, .11*r, (63, 93, 65), .4)
    paint.stroke([(x+.11*r, y), (x-.06*r, y-.76*r)], max(1.05, r*.19), (101, 82, 55))
    cy = y-1.03*r
    paint.ellipse(x+.06*r, cy+.12*r, r, .78*r, deep)
    paint.ellipse(x-.37*r, cy, .72*r, .75*r, deep)
    paint.ellipse(x-.10*r, cy-.16*r, .91*r, .78*r, mid)
    paint.ellipse(x-.40*r, cy-.26*r, .66*r, .59*r, mid)
    paint.ellipse(x-.34*r, cy-.42*r, .59*r, .44*r, sun)
    paint.ellipse(x+.43*r, cy+.16*r, .59*r, .54*r, mid)
    paint.ellipse(x+.48*r, cy+.33*r, .49*r, .38*r, deep)
    if r > 10:
        for index in range(3 + int(r/8)):
            fx = rng.uniform(-.78, .72)
            fy = rng.uniform(-.47, .38)
            size = max(.8, r*rng.uniform(.034, .062))
            ink = (225, 167, 83) if index % 3 else (189, 128, 66)
            paint.ellipse(x+fx*r, cy+fy*r, size, size*.92, ink)


def orchard(paint, road, rng):
    trees = []
    depths = (0, .035, .081, .14, .216, .31, .427, .571, .744, .945, 1.17)
    for side, pivot, ends in (
        (-1, 320, (-552, -370, -196, -21, 142)),
        (1, 430, (530, 689, 856, 1028, 1200)),
    ):
        for j, end in enumerate(ends):
            for depth in depths:
                t = depth + .014*j
                y = 643 + 367*t + rng.uniform(-2, 2)
                x = pivot+(end-pivot)*(.055+.945*t) + rng.uniform(-4, 4)
                r = (5.6 + 37*t)*rng.uniform(.85, 1.10)
                center, width = road[min(1003, max(620, round(y)))]
                if x+r < -15 or x-r > WIDTH+15 or y-r > HEIGHT+30:
                    continue
                if side*(x-center) < width + r*.93:
                    continue
                trees.append((y, x, r, rng.random()))
    trees.extend((
        (656, 120, 11, .35), (658, 161, 12, .73), (661, 181, 12, .43),
        (663, 203, 10, .55), (665, 228, 11, .22),
        (663, 502, 11, .5), (664, 532, 14, .15), (670, 556, 13, .4),
        (671, 580, 14, .55), (675, 600, 12, .43),
    ))
    houses = [(668, 687, .81), (682, 647, .96), (688, 711, 1.11)]
    for y, kind, x, size, variation in sorted(
        [(y, 0, x, r, variant) for y, x, r, variant in trees] +
        [(y, 1, x, s, 0) for y, x, s in houses]
    ):
        if kind == 0:
            tree(paint, x, y, size, variation, rng)
        else:
            cottage(paint, x, y, size)


def visitors(paint):
    ink = (43, 70, 59)

    def walker(x, y, s, coat, stride):
        def stroke(points, width, color):
            paint.stroke([(x+a*s, y+b*s) for a, b in points], width*s, color)

        paint.ellipse(x+4*s, y, 7*s, 1.9*s, (92, 96, 71), .48)
        stroke([(0, -8), (-3*stride, -1)], 2, ink)
        stroke([(0, -8), (4*stride, 0)], 2, ink)
        stroke([(-.5, -15), (0, -7.5)], 4.8, coat)
        stroke([(-1, -13), (-4*stride, -8.5)], 1.6, coat)
        stroke([(1, -13), (3*stride, -9)], 1.6, coat)
        paint.ellipse(x-.5*s, y-19*s, 2.25*s, 2.6*s, ink)
        paint.ellipse(x-.8*s, y-20.3*s, 3.1*s, 1.05*s, (232, 201, 143))

    for x, y, s, coat, stride in (
        (383, 668, .58, (193, 106, 73), 1),
        (391, 677, .64, (67, 95, 77), -1),
        (446, 745, .86, (53, 96, 78), 1),
        (458, 754, .92, (183, 89, 60), -1),
        (410, 897, 1.34, (54, 98, 87), 1),
    ):
        walker(x, y, s, coat, stride)
    for x, y, s in ((416, 699, .64), (533, 793, .95)):
        paint.ellipse(x+9*s, y+1, 17*s, 2.5*s, (70, 88, 65), .34)
        for offset in (2, 21):
            paint.stroke([(x+offset*s, y-7*s), (x+offset*s, y)], 1.9*s, ink)
        paint.stroke([(x, y-7*s), (x+24*s, y-7*s)], 3*s, (131, 79, 55))
        paint.stroke([(x, y-13*s), (x+24*s, y-13*s)], 2.4*s, (153, 91, 61))


def grain(rgb):
    # A common offset in all three inks gives paper grain without color speckle.
    rng = Random(7153)
    noise = rng.randbytes(WIDTH*HEIGHT)
    shifts = (-4, -2, -1, 0, 0, 1, 2, 4)
    for i, sample in enumerate(noise):
        delta = shifts[sample >> 5]
        offset = i*3
        rgb[offset] += delta
        rgb[offset+1] += delta
        rgb[offset+2] += delta


def png_chunk(kind, data):
    return pack(">I", len(data)) + kind + data + pack(">I", crc32(kind+data))


def encode_png(rgb):
    stride = WIDTH*3
    filtered = bytearray()
    for y in range(HEIGHT):
        row = rgb[y*stride:(y+1)*stride]
        filtered.append(1)  # Sub, relative to the same channel of the previous pixel.
        filtered.extend(row[:3])
        filtered.extend((value-left) & 255 for value, left in zip(row[3:], row))
    header = pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header)
            + png_chunk(b"IDAT", compress(filtered, 9)) + png_chunk(b"IEND", b""))


def main():
    paint = Painter()
    backdrop(paint)
    grove_floor(paint)
    rock_loop(paint)
    road = lane()
    promenade(paint, road)
    orchard(paint, road, Random(20261121))
    visitors(paint)
    title(paint)
    grain(paint.rgb)
    destination = Path("/output/entry.png")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encode_png(paint.rgb))


if __name__ == "__main__":
    main()
