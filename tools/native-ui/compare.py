"""Convert native RGBA captures and compare with frozen reference images."""
import json,argparse
from pathlib import Path
from PIL import Image,ImageChops,ImageStat
p=argparse.ArgumentParser();p.add_argument('--captures',type=Path,default=Path('/tmp'));p.add_argument('--output',type=Path,default=Path('build/native-ui/comparison'));a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
results={}
for path in a.captures.glob('native-*.pam'):
 header,data=path.read_bytes().split(b'ENDHDR\n',1);meta={line.split()[0]:line.split()[1] for line in header.splitlines()[1:]};im=Image.frombytes('RGBA',(int(meta[b'WIDTH']),int(meta[b'HEIGHT'])),data);im.save(a.output/(path.stem+'.png'))
 page=path.stem.removeprefix('native-');ref=Path('build/native-ui')/('reference-1-'+page+'.png')
 if not ref.exists():continue
 original=Image.open(ref).convert('RGB');actual=im.convert('RGB');d=ImageChops.difference(actual,original)
 red,green,blue=d.split();histogram=ImageChops.lighter(ImageChops.lighter(red,green),blue).histogram()
 results[page]={'mae_rgb_255':round(sum(ImageStat.Stat(d).mean)/3,4),'pixels_with_channel_delta_over_8_percent':round(sum(histogram[9:])/(im.width*im.height)*100,4)}
 d.point(lambda value:min(255,value*4)).save(a.output/('difference-'+page+'.png'))
(a.output/'comparison.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results))
