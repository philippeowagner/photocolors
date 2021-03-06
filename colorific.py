#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Colorific: http://99designs.com/tech-blog/blog/2012/05/11/color-analysis/

"""
Detect the main colors used in an image.
"""

import os
from collections import Counter, namedtuple
from operator import itemgetter, mul, attrgetter
from StringIO import StringIO
import colorsys
from colormath.color_objects import RGBColor

try:
    from PIL import Image, ImageChops
except:
    import Image, ImageChops

Color = namedtuple('Color', ['value', 'prominence'])
Palette = namedtuple('Palette', 'colors bgcolor')

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# algorithm tuning defaults
N_QUANTIZED = 200       # start with an adaptive palette of this size
MIN_DISTANCE = 10.0     # min distance to consider two colors different
MIN_PROMINENCE = 0.01   # ignore if less than this proportion of image
MIN_SATURATION = 0.05   # ignore if not saturated enough
MAX_COLORS = 5          # keep only this many colors
BACKGROUND_PROMINENCE = 0.4     # level of prominence indicating a bg color


def load_image(data=None, path=None):
    if data:
        return Image.open(StringIO(data))
    elif path:
        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise Exception('Invalid photo file path: %s', path)
        return Image.open(path)


def distance(c1, c2):
    "Calculate the visual distance between the two colors."
    return RGBColor(*c1).delta_e(RGBColor(*c2), method='cmc')


def rgb_to_hex(color):
    return '%.02x%.02x%.02x' % color


def hex_to_rgb(color):
    assert color.startswith('#') and len(color) == 7
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))


def norm_color(c):
    r, g, b = c
    return (r / 255.0, g / 255.0, b / 255.0)


def detect_background(im, colors, to_canonical):
    # more then half the image means background
    if colors[0].prominence >= BACKGROUND_PROMINENCE:
        return colors[1:], colors[0]

    # work out the background color
    w, h = im.size
    points = [(0, 0), (0, h / 2), (0, h - 1), (w / 2, h - 1), (w - 1, h - 1),
            (w - 1, h / 2), (w - 1, 0), (w / 2, 0)]
    edge_dist = Counter(im.getpixel(p) for p in points)

    (majority_col, majority_count), = edge_dist.most_common(1)
    if majority_count >= 3:
        # we have a background color
        canonical_bg = to_canonical[majority_col]
        bg_color, = [c for c in colors if c.value == canonical_bg]
        colors = [c for c in colors if c.value != canonical_bg]
    else:
        # no background color
        bg_color = None

    return colors, bg_color


def meets_min_saturation(c, threshold):
    return colorsys.rgb_to_hsv(*norm_color(c.value))[1] > threshold


def autocrop(im, bgcolor):
    "Crop away a border of the given background color."
    if im.mode != "RGB":
        im = im.convert("RGB")
    bg = Image.new("RGB", im.size, bgcolor)
    diff = ImageChops.difference(im, bg)
    bbox = diff.getbbox()
    if bbox:
        return im.crop(bbox)
    return im  # no contents, don't crop to nothing


def extract_colors(im, min_saturation=MIN_SATURATION,
        min_distance=MIN_DISTANCE, max_colors=MAX_COLORS,
        min_prominence=MIN_PROMINENCE, n_quantized=N_QUANTIZED):
    """
    Determine what the major colors are in the given image.
    """

    # get point color count
    if im.mode != 'RGB':
        im = im.convert('RGB')
    im = autocrop(im, WHITE)  # assume white box
    im = im.convert('P', palette=Image.ADAPTIVE, colors=n_quantized).convert('RGB')
    data = im.getdata()
    dist = Counter(data)
    n_pixels = mul(*im.size)

    # aggregate colors
    to_canonical = {WHITE: WHITE, BLACK: BLACK}
    aggregated = Counter({WHITE: 0, BLACK: 0})
    sorted_cols = sorted(dist.iteritems(), key=itemgetter(1), reverse=True)
    for c, n in sorted_cols:
        if c in aggregated:
            # exact match!
            aggregated[c] += n
        else:
            d, nearest = min((distance(c, alt), alt) for alt in aggregated)
            if d < min_distance:
                # nearby match
                aggregated[nearest] += n
                to_canonical[c] = nearest
            else:
                # no nearby match
                aggregated[c] = n
                to_canonical[c] = c

    # order by prominence
    colors = sorted((Color(c, n / float(n_pixels)) \
                for (c, n) in aggregated.iteritems()),
            key=attrgetter('prominence'),
            reverse=True)

    colors, bg_color = detect_background(im, colors, to_canonical)

    # keep any color which meets the minimum saturation
    sat_colors = [c for c in colors if meets_min_saturation(c, min_saturation)]
    if bg_color and not meets_min_saturation(bg_color, min_saturation):
        bg_color = None
    if sat_colors:
        colors = sat_colors
    else:
        # keep at least one color
        colors = colors[:1]

    # keep any color within 10% of the majority color
    colors = [c for c in colors if c.prominence >= colors[0].prominence
            * min_prominence][:max_colors]

    palette = Palette(colors, bg_color)
    # returns a palette of 3 if there are not 5 colors
    return [rgb_to_hex(c.value) for c in palette.colors[:(5, 3)[len(palette.colors) < 5]]]
