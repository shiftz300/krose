"""Freeze the approved editor at native size; only used during UI authoring."""
import argparse, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'build/native-ui');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
html=(ROOT/'build/plugin/src/plugin/editor.html').read_text()
html=html.replace('<script>','<script>window.IPlugSendMsg=()=>{};',1)
(a.output/'reference.html').write_text(html)
rect_script="""(()=>{const b=document.querySelector('.instrument').getBoundingClientRect();return {size:[b.width,b.height],scale:devicePixelRatio,elements:[...document.querySelectorAll('.instrument button,.instrument input,.instrument select,.lcd,.lcd-bezel,.program-picker,.fader-track,.fader output,.readout,.preset-title,.lcd-top,.lcd-footer,.caption,.fx-hit')].filter(e=>e.getClientRects().length).map(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {id:e.id,tag:e.tagName,classes:e.className?.baseVal??e.className,data:{...e.dataset},text:e.textContent,value:e.value,disabled:e.disabled,rect:[r.x,r.y,r.width,r.height],font:s.font,color:s.color,letterSpacing:s.letterSpacing}})};})()"""
jobs=[{'name':'layout.json','json':True,'script':rect_script}]
for program in [0,1,2,3,4]:
 for page in ['main','tone','fx','arp']:
  script=f"window.kroseNative.receive('Program',5,{program});document.querySelector('.lcd-tab[data-page={page}]').click()"
  jobs.append({'name':f'reference-{program}-{page}.png','script':script})
jobs.extend([{'name':'reference-folded.png','script':"window.kroseNative.receive('Program',5,1);document.querySelector('.lcd-tab[data-page=main]').click();document.querySelector('.fx-lettering').click()"},{'name':'layout-folded.json','json':True,'script':rect_script}])
(a.output/'jobs.json').write_text(json.dumps(jobs))
manifest={'inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'src/plugin/editor/web').glob('*'))},'logicalSize':[1472,648],'capture':'WKWebView at native display scale; no stylesheet or layout modifications','referencePrograms':[0,1,2,3,4]}
(a.output/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(a.output)
