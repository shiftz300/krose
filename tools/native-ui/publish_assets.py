"""Validate and publish the authoring capture into versioned native resources."""
import hashlib,json,shutil
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];source=ROOT/'build/native-ui'
dest=ROOT/'src/plugin/editor/native/assets';dest.mkdir(parents=True,exist_ok=True)
index=json.loads((source/'asset-index.json').read_text())
for item in index:
    path=source/'assets'/(item['name']+'.png')
    with Image.open(path) as image:
        expected=(round(item['rect'][2]*2),round(item['rect'][3]*2))
        if image.size!=expected or image.mode!='RGBA' or not image.getbbox():
            raise RuntimeError(f'Invalid capture {path}: {image.size}, expected {expected}')
    item['file']=item['name']+'@2x.png'
    shutil.copyfile(path,dest/item['file'])
    item['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
for name in ['material-expanded','material-folded']:
    path=source/'assets'/(name+'.png')
    with Image.open(path) as image:
        if image.size!=(2944,1296):raise RuntimeError('Panel dimensions changed')
    shutil.copyfile(path,dest/(name+'@2x.png'))
    index.append({'name':name,'file':name+'@2x.png','rect':[0,0,1472,648],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(dest/'manifest.json').write_text(json.dumps({'scale':2,'assets':index},indent=2)+'\n')
verification=ROOT/'docs/verification/native-ui'
for name in ['layout.json','layout-folded.json','source-manifest.json','reference-1-main.png','reference-folded.png']:
    shutil.copyfile(source/name,verification/name)
print(f'Published {len(index)} assets; reference hashes and geometry retained')
