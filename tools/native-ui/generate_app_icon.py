"""Regenerate frozen application icons with Pillow; not a build dependency.

Uses a custom bold Roman serif K, with warm marble on a graphite tile.
All sizes are rendered from the same geometry at 2x before downsampling.
"""
from io import BytesIO
import json
import math
from pathlib import Path
import re
import struct

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'src/plugin/resources'
# Original outlined letterform, independent of installed fonts and the company logo.
MARK = (
    'M248 224H506L506 248C450 248 440 258 440 292L440 504L640 286'
    'C661 263 651 248 604 248L604 224H808L808 248'
    'C766 248 746 260 718 290L548 469L742 748'
    'C758 772 775 776 808 776L808 800H562L562 776'
    'C606 776 615 767 597 738L457 548L440 566L440 732'
    'C440 766 450 776 506 776L506 800H248L248 776'
    'C302 776 312 766 312 732L312 292C312 258 302 248 248 248Z'
)
SCALE = 2
LETTER_SCALE = .82
MARK_TRANSFORM = 'translate(512 512) scale(.82) translate(-528 -512)'


def contour(path):
    tokens = iter(re.findall(r'[MCLHZ]|-?\d+(?:\.\d+)?', path))
    points = []
    for command in tokens:
        if command in ('M', 'L'):
            point = (float(next(tokens)), float(next(tokens)))
            points.append(point)
        elif command == 'H':
            point = (float(next(tokens)), point[1])
            points.append(point)
        elif command == 'C':
            a = (float(next(tokens)), float(next(tokens)))
            b = (float(next(tokens)), float(next(tokens)))
            end = (float(next(tokens)), float(next(tokens)))
            start = point
            for i in range(1, 65):
                t = i / 64
                points.append(tuple((1-t)**3 * start[j] + 3*(1-t)**2*t*a[j]
                                    + 3*(1-t)*t*t*b[j] + t**3*end[j] for j in (0, 1)))
            point = end
    return [(round((512 + (x - 528)*LETTER_SCALE)*SCALE),
             round((512 + (y - 512)*LETTER_SCALE)*SCALE)) for x, y in points]


def shifted(mask, x, y):
    result = Image.new('L', mask.size)
    result.paste(mask, (round(x*SCALE), round(y*SCALE)))
    return result


def overlay(image, mask, color, opacity):
    layer = Image.new('RGBA', image.size, color)
    layer.putalpha(mask.point(lambda value: round(value*opacity)))
    image.alpha_composite(layer)


def main():
    size = 1024*SCALE
    icon = Image.new('RGBA', (size, size))
    tile = Image.new('L', (size, size))
    ImageDraw.Draw(tile).rounded_rectangle((64*SCALE, 64*SCALE, 960*SCALE, 960*SCALE),
                                           radius=196*SCALE, fill=255)
    background = Image.new('RGBA', (size, size))
    draw = ImageDraw.Draw(background)
    for y in range(size):
        t = min(1, max(0, (y/SCALE-64)/896))
        color = tuple(round(a+(b-a)*t) for a, b in zip((75, 77, 81), (40, 42, 46)))
        draw.line((0, y, size, y), fill=(*color, 255))
    icon.paste(background, (0, 0), tile)
    overlay(icon, ImageChops.subtract(tile, shifted(tile, 0, 2)), '#ffffff', .22)
    overlay(icon, ImageChops.subtract(tile, shifted(tile, 0, -2)), '#000000', .24)
    mask = Image.new('L', (size, size))
    pen = ImageDraw.Draw(mask)
    pen.polygon(contour(MARK), fill=255)
    marble = Image.new('RGBA', (size, size), '#e5d3c8')
    pen = ImageDraw.Draw(marble)
    veins = []
    for i in range(-5, 12):
        points = [(x, 75*i + x*.63 + 17*math.sin(x/83+i)
                   + 9*math.sin(x/31+i*.7)) for x in range(0, 1025, 4)]
        for width, color in ((12, '#e0ccbf'), (4, '#ceb4a2'), (1, '#b69882')):
            pen.line([(round(x*SCALE), round(y*SCALE)) for x, y in points],
                     fill=color, width=width*SCALE)
            veins.append('<polyline points="' + ' '.join(f'{x:.1f},{y:.1f}' for x, y in points)
                         + f'" fill="none" stroke="{color}" stroke-width="{width}"/>')
    # Unmasked canvas and an unlit foreground: macOS owns the rounded enclosure,
    # lighting and appearance variants for the layered icon.
    bundle = DEST / 'Krose.icon'
    (bundle / 'Assets').mkdir(parents=True, exist_ok=True)
    foreground = marble.copy()
    foreground.putalpha(mask)
    foreground.resize((1024, 1024), Image.Resampling.LANCZOS).save(
        bundle / 'Assets/K.png', optimize=True)
    manifest = {
        'fill-specializations': [
            {'value': {'linear-gradient': ['srgb:0.29412,0.30196,0.31765,1',
                                           'srgb:0.15686,0.16471,0.18039,1']}},
            {'appearance': 'dark', 'value': {'linear-gradient': [
                'srgb:0.09804,0.10196,0.11373,1', 'srgb:0.03529,0.03922,0.04706,1']}},
            {'appearance': 'tinted', 'value': 'automatic'},
        ],
        'groups': [{
            'name': 'Marble K',
            'layers': [{'name': 'K', 'image-name': 'K.png', 'glass': True}],
            'shadow': {'kind': 'neutral', 'opacity': .25},
            'specular': True,
            'translucency': {'enabled': False, 'value': .5},
        }],
        'supported-platforms': {'squares': ['macOS']},
    }
    (bundle / 'icon.json').write_text(json.dumps(manifest, indent=2) + '\n')
    # Broad cast shadow, close contact shadow, then a fine polished stone bevel.
    for dy, blur, opacity in ((18, 18, .36), (4, 3, .28)):
        shadow = shifted(mask, 0, dy).filter(ImageFilter.GaussianBlur(blur*SCALE))
        overlay(icon, ImageChops.multiply(shadow, tile), '#08090c', opacity)
    icon.paste(marble, (0, 0), mask)
    overlay(icon, ImageChops.subtract(mask, shifted(mask, 1.5, 2)), '#fff9ef', .68)
    overlay(icon, ImageChops.subtract(mask, shifted(mask, -1, -2)), '#624e42', .34)
    icon = icon.resize((1024, 1024), Image.Resampling.LANCZOS)
    icon.save(DEST / 'Krose.png', optimize=True)
    icon.save(DEST / 'Krose.ico', sizes=[(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    # PNG-backed ICNS entries cover standard and Retina sizes without iconutil.
    chunks = []
    for tag, n in ((b'icp4', 16), (b'icp5', 32), (b'icp6', 64), (b'ic07', 128),
                   (b'ic08', 256), (b'ic09', 512), (b'ic10', 1024),
                   (b'ic11', 32), (b'ic12', 64), (b'ic13', 256), (b'ic14', 512)):
        png = BytesIO()
        icon.resize((n, n), Image.Resampling.LANCZOS).save(png, format='PNG')
        data = png.getvalue()
        chunks.append(tag + struct.pack('>I', len(data)+8) + data)
    body = b''.join(chunks)
    (DEST / 'Krose.icns').write_bytes(b'icns' + struct.pack('>I', len(body)+8) + body)
    (DEST / 'Krose.svg').write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">\n'
        '<defs>\n'
        '<linearGradient id="tile" x2="0" y2="1"><stop stop-color="#4b4d51"/>'
        '<stop offset="1" stop-color="#282a2e"/></linearGradient>\n'
        f'<path id="letter" transform="{MARK_TRANSFORM}" d="{MARK}"/>\n'
        '<clipPath id="mark"><use href="#letter"/></clipPath>\n'
        '<filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">'
        '<feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#08090c" flood-opacity=".36"/>'
        '<feDropShadow dx="0" dy="4" stdDeviation="3" flood-color="#08090c" flood-opacity=".28"/>'
        '</filter>\n'
        '<filter id="highlight"><feOffset in="SourceAlpha" dx="1.5" dy="2" result="offset"/>'
        '<feComposite in="SourceAlpha" in2="offset" operator="out" result="edge"/>'
        '<feFlood flood-color="#fff9ef" flood-opacity=".68"/>'
        '<feComposite in2="edge" operator="in"/></filter>\n'
        '<filter id="bevel"><feOffset in="SourceAlpha" dx="-1" dy="-2" result="offset"/>'
        '<feComposite in="SourceAlpha" in2="offset" operator="out" result="edge"/>'
        '<feFlood flood-color="#624e42" flood-opacity=".34"/>'
        '<feComposite in2="edge" operator="in"/></filter></defs>\n'
        '<rect x="64" y="64" width="896" height="896" rx="196" fill="url(#tile)"/>'
        '<rect x="65" y="65" width="894" height="894" rx="195" fill="none" stroke="#ffffff" stroke-opacity=".12" stroke-width="2"/>\n'
        '<use href="#letter" fill="#e5d3c8" filter="url(#shadow)"/>\n'
        '<g clip-path="url(#mark)"><rect width="1024" height="1024" fill="#e5d3c8"/>\n'
        + '\n'.join(veins) + '\n</g>\n'
        '<use href="#letter" filter="url(#highlight)"/>'
        '<use href="#letter" filter="url(#bevel)"/></svg>\n')
    print('Generated Krose.icon and SVG/PNG/ICO/ICNS fallbacks')


if __name__ == '__main__':
    main()
