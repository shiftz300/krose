"""Capture the remaining fixed geometry and material variants for native drawing."""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];out=ROOT/'build/native-ui'
exec((ROOT/'tools/native-ui/assets.py').read_text().replace("ROOT = Path(__file__).resolve().parents[2]",'ROOT = ROOT'))
# Remove material jobs until individual captures finish.
jobs=jobs[:-2]
for note in [38,37]:
 s=f'[data-midi="{note}"]';e=next(e for e in layout['elements'] if e['data'].get('midi')==str(note));x,y,w,h=e['rect'];r=[math.floor(x)-3,y-3,math.ceil(x+w)-math.floor(x)+6,h+8]
 for on in [False,True]:capture(('white' if note==38 else 'black')+('-down' if on else '-up'),s,r,f"document.querySelector('{s}').classList.toggle('is-down',{str(on).lower()})")
for name in ['kf-oct-down','kf-oct-up']:
 e=next(e for e in layout['elements'] if e['id']==name);x,y,w,h=e['rect'];capture(name,'#'+name,[math.floor(x)-3,y-3,math.ceil(x+w)-math.floor(x)+6,h+8])
capture('pitch-mark','#kf-pitch .wheel-mark',[56,491,32,12])
capture('fader-thumb','#kf-attack',[1037,185,40,29])
# One baked strip per page; preserves the 45-degree joins exactly.
for page in ['main','tone','fx','arp']:
 capture('tabs-'+page,'.lcd-tabs',[432,115,540,22],f"document.querySelector('.lcd-tab[data-page={page}]').click()")
# Entire static base variants; dynamic controls are drawn on top by C++.
for program in range(5):
 jobs.append({'name':f'material-{program}.png','script':reset.replace("receive('Program',5,1)",f"receive('Program',5,{program})")+hide})
jobs.append({'name':'material-folded.png','script':reset+hide+"if(document.querySelector('.fx-lettering').getAttribute('aria-expanded')==='true')document.querySelector('.fx-lettering').click();document.querySelector('#kf-effect-view').style.visibility='hidden';null"})
# Capture the actual raster fonts once; no platform font substitution at runtime.
chars=''.join(chr(i) for i in range(32,127))+'−×·→—名称或编号全部音色库类型没有匹配的关闭浏览'
fonts=[('lcd35','35px KroseLCDPixel',35),('lcd16','16px KroseLCDPixel',16),('light16','16px KroseLCDPixel',16),('light14','14px KroseLCDPixel',14),('lcd15','15px KroseLCDPixel',15),('lcd14','14px KroseLCDPixel',14),('lcd13','13px KroseLCDPixel',13),('mono12','12px ui-monospace,Menlo,monospace',12),('mono10','10px ui-monospace,Menlo,monospace',10),('arial15','15px Arial',15),('search15','15px Arial',15),('placeholder15','15px Arial',15),('arial14','14px Arial',14),('arial13','13px Arial',13),('arial9','9px Arial',9)]
fontmeta=[]
for name,font,size in fonts:
 script="""(()=>{[...document.querySelectorAll('body style')].forEach(s=>document.head.append(s));document.body.innerHTML='';document.documentElement.style.cssText='background:transparent!important;margin:0;padding:0';document.body.style.cssText='background:transparent!important;margin:0;padding:0';const c=document.createElement('canvas');c.width=1280;c.height=1232;c.style='width:640px;height:616px';document.body.append(c);const x=c.getContext('2d');x.scale(2,2);x.font=FONT;x.fillStyle=COLOR;const chars=CHARS;window.fontMetrics={chars,font:FONT,size:SIZE,advances:[]};[...chars].forEach((ch,i)=>{x.fillText(ch,(i%10)*64+4,Math.floor(i/10)*44+SIZE);window.fontMetrics.advances.push(x.measureText(ch).width)});return null})()""".replace('FONT',json.dumps(font)).replace('COLOR',json.dumps('#394e62' if name.startswith('lcd') else '#aebcc7' if name.startswith('mono') else '#222222' if name=='search15' else '#aaaaaa' if name=='placeholder15' else '#d8e2e9' if name.startswith('light') else '#627570' if name=='arial9' else '#e3e3e3')).replace('CHARS',json.dumps(chars)).replace('SIZE',str(size))
 jobs.append({'name':'font-'+name+'.png','script':script,'rect':[0,0,640,616]})
 jobs.append({'name':'font-'+name+'.json','script':'window.fontMetrics','json':True})
(out/'complete-jobs.json').write_text(json.dumps(jobs));(out/'complete-index.json').write_text(json.dumps(assets,indent=2))
print(len(jobs),'jobs')
