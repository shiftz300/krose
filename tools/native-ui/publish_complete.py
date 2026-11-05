import json,hashlib,shutil
from pathlib import Path
from PIL import Image
from compact_fonts import pack_font
R=Path(__file__).resolve().parents[2];work=R/'build/native-ui';dest=R/'src/plugin/editor/native/assets'
index=json.loads((work/'complete-index.json').read_text())
# Validate the complete capture set before replacing any runtime image.
for folder,jobs in [('complete','complete-jobs.json'),('fields','field-jobs.json')]:
 for job in json.loads((work/jobs).read_text()):
  if job.get('json'):continue
  rect=job.get('rect',[0,0,1472,648]);expected=(round(rect[2]*2),round(rect[3]*2))
  with Image.open(work/folder/job['name']) as im:
   if im.size!=expected:raise ValueError(f"{job['name']}: expected 2x {expected}, got {im.size}")
for e in index:
 p=work/'complete'/(e['name']+'.png');shutil.copyfile(p,dest/(e['name']+'@2x.png'))
for i in range(5):
 im=Image.open(work/'complete'/f'material-{i}.png');im.crop((0,38,856,702)).save(dest/f'fx-region-{i}@2x.png')
im=Image.open(work/'complete/material-1.png');im.crop((0,38,2944,50)).save(dest/'expanded-strip@2x.png')
shutil.copyfile(work/'complete/material-folded.png',dest/'native-base@2x.png')
fonts={}
for p in (work/'complete').glob('font-*.png'):
 fonts[p.stem[5:]]=pack_font(p,json.loads(p.with_suffix('.json').read_text()),dest/(p.stem+'@2x.png'))
for p in (work/'fields').glob('*.png'):shutil.copyfile(p,dest/(p.stem+'@2x.png'))
metadata={'fxHits':{str(i):json.loads((work/'fields'/f'hits-{i}.json').read_text()) for i in range(5)},'assets':index,'fonts':fonts,'fields':{name:json.loads((work/'fields'/('layout-'+name+'.json')).read_text()) for name in ['tone','arp','fx']}}
def publish_fx_faces(module_hits, dest):
    """Build one 2x atlas from the existing glass faces and three new traces."""
    from math import hypot, pi, sin, tanh
    from PIL import ImageDraw, ImageEnhance, ImageOps

    size = 108
    names = ('eq', 'compressor', 'limiter', 'drive', 'exciter',
             'chorus', 'delay', 'hall', 'plate')
    originals = {
        'eq': ('1', 'PARAMETRIC EQ'), 'limiter': ('1', 'MASTERING LIMITER'),
        'exciter': ('3', 'STEREO EXCITER'), 'chorus': ('3', 'STEREO CHORUS'),
        'hall': ('1', 'HALL'), 'plate': ('2', 'PLATE'),
    }

    def capture(name):
        group, title = originals[name]
        rect = next(hit['rect'] for hit in module_hits[group]
                    if hit['kind'] == 'module' and hit['label'].split(' · ')[-1] == title)
        x, y, w, h = rect
        left, top = round(2 * (x + w * .1)), round(2 * (y - 19 + h * .1))
        with Image.open(dest / f'fx-region-{group}@2x.png') as source:
            return source.crop((left, top, left + size, top + size)).convert('RGB')

    def trace(name):
        tints = {'compressor': (59, 51, 38),
                 'drive': (60, 42, 38), 'delay': (35, 51, 60)}
        color = tints[name]
        face = Image.new('RGB', (size, size))
        face.putdata([
            tuple(round(c * (.78 + .22 * sin(pi * y / (size - 1))) +
                        12 * max(0, 1 - hypot(x - size / 2, y + 4) / 49))
                  for c in color)
            for y in range(size) for x in range(size)
        ])
        draw = ImageDraw.Draw(face)
        for grid in (25, 44, 63, 82):
            draw.line((14, grid, 93, grid), fill=(70, 72, 68))
            draw.line((grid, 15, grid, 93), fill=(70, 72, 68))
        if name == 'compressor':
            draw.line((19, 88, 86, 21), fill=(119, 108, 77), width=2)
            draw.line([(19, 88), (49, 58), (55, 53), (62, 50), (91, 40)],
                      fill=(231, 192, 119), width=4, joint='curve')
            draw.ellipse((51, 49, 59, 57), fill=(246, 217, 155))
        elif name == 'drive':
            waveform = [(x, 54 - 23 * tanh(2.7 * sin((x - 12) * 2 * pi / 57)))
                        for x in range(12, 97)]
            draw.line(waveform, fill=(221, 128, 103), width=5, joint='curve')
            draw.line(waveform, fill=(254, 172, 139), width=2, joint='curve')
        else:
            draw.line((12, 76, 96, 76), fill=(93, 130, 144), width=2)
            for x, h, ink in ((17, 52, (150, 220, 238)), (42, 36, (121, 186, 210)),
                              (67, 23, (101, 153, 180)), (89, 13, (84, 125, 147))):
                draw.line([(x, 76), (x + 3, 76 - h), (x + 7, 76)], fill=ink,
                          width=3, joint='curve')
        return face

    atlas = Image.new('RGB', (size * len(names), size * 2))
    for column, name in enumerate(names):
        face = capture(name) if name in originals else trace(name)
        atlas.paste(face, (size * column, 0))
        grey = ImageEnhance.Brightness(ImageOps.grayscale(face)).enhance(.56)
        atlas.paste(grey, (size * column, size))
    atlas.save(dest / 'fx-faces@2x.png', optimize=True)

publish_fx_faces(metadata['fxHits'], dest)
(dest/'native-data.json').write_text(json.dumps(metadata,ensure_ascii=False,separators=(',',':'))+'\n')
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dest.glob('*.png'))}
(dest/'files.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(len(manifest),'PNG resources')
