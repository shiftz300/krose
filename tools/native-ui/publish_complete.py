import json,hashlib,shutil
from pathlib import Path
from PIL import Image
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
 shutil.copyfile(p,dest/(p.stem+'@2x.png'));fonts[p.stem[5:]]=json.loads(p.with_suffix('.json').read_text())
for p in (work/'fields').glob('*.png'):shutil.copyfile(p,dest/(p.stem+'@2x.png'))
metadata={'fxHits':{str(i):json.loads((work/'fields'/f'hits-{i}.json').read_text()) for i in range(5)},'assets':index,'fonts':fonts,'fields':{name:json.loads((work/'fields'/('layout-'+name+'.json')).read_text()) for name in ['tone','arp','fx']}}
(dest/'native-data.json').write_text(json.dumps(metadata,ensure_ascii=False,separators=(',',':'))+'\n')
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dest.glob('*.png'))}
(dest/'files.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(len(manifest),'PNG resources')
