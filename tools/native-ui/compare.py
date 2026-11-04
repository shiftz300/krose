"""Convert native RGBA captures and compare with frozen reference images."""
import json,argparse
from pathlib import Path
import numpy as np
from PIL import Image
p=argparse.ArgumentParser();p.add_argument('--captures',type=Path,default=Path('/tmp'));p.add_argument('--output',type=Path,default=Path('build/native-ui/comparison'));a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
results={}
for path in a.captures.glob('native-*.pam'):
 header,data=path.read_bytes().split(b'ENDHDR\n',1);meta={line.split()[0]:line.split()[1] for line in header.splitlines()[1:]};im=Image.frombytes('RGBA',(int(meta[b'WIDTH']),int(meta[b'HEIGHT'])),data);im.save(a.output/(path.stem+'.png'))
 page=path.stem.removeprefix('native-');ref=Path('build/native-ui')/('reference-1-'+page+'.png')
 if not ref.exists():continue
 original=Image.open(ref).convert('RGB');actual=im.convert('RGB');d=np.abs(np.asarray(actual,dtype=float)-np.asarray(original,dtype=float));results[page]={'mae_rgb_255':round(float(d.mean()),4),'pixels_with_channel_delta_over_8_percent':round(float((d.max(axis=2)>8).mean()*100),4)}
 Image.fromarray(np.uint8(np.clip(d*4,0,255))).save(a.output/('difference-'+page+'.png'))
(a.output/'comparison.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results))
