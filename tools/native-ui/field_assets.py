"""Freeze native field chrome, FX read-only pages and their exact hit regions."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];p=ROOT/'build/native-ui';jobs=[]
rect=json.loads((p/'jobs.json').read_text())[0]['script']
for page in ['tone','arp','fx']:
 jobs.append({'name':'layout-'+page+'.json','json':True,'script':"window.kroseNative.receive('Program',5,1);document.querySelector('.lcd-tab[data-page="+page+"]').click();"+rect})
for program,count in [(0,1),(1,4),(2,2),(3,3),(4,4)]:
 for slot in range(count):
  script=f"window.kroseNative.receive('Program',5,{program});document.querySelector('.lcd-tab[data-page=fx]').click();document.querySelectorAll('#kf-fx-slots button')[{slot}]?.click();"
  jobs.append({'name':f'fx-{program}-{slot}.png','rect':[436,168,532,110],'script':script})
  if not slot:jobs.append({'name':f'hits-{program}.json','json':True,'script':"[...document.querySelectorAll('#kf-fx-slots button,.fx-hit')].map(e=>{let r=e.getBoundingClientRect();return {rect:[r.x,r.y,r.width,r.height],label:e.getAttribute('aria-label'),kind:e.classList.contains('fx-hit')?'module':'slot'}})"})
# Let CSS draw the same field borders, arrows and backgrounds as the reference.
for name,page,selector,r in [('number-tone','tone','#kf-tone [data-bind=cutoff]',[621.5,168,68,24]),('number-arp','arp','#kf-arp [data-bind=gate]',[625,190,68,18]),('select-tone','tone','#kf-tone select',[581.5,232,108,24]),('select-arp','arp','#kf-pattern',[585,168,108,18])]:
 css='html,body,#krose-fixed-ui .instrument{background:transparent!important;box-shadow:none!important;border-color:transparent!important}#krose-fixed-ui .instrument *{visibility:hidden!important}#krose-fixed-ui .instrument '+selector+'{visibility:visible!important;color:transparent!important}'
 script="document.getElementById('field-isolate')?.remove();document.querySelector('.lcd-tab[data-page="+page+"]').click();(()=>{let e=document.querySelector("+json.dumps(selector)+");if(e.tagName==='INPUT')e.value='';let s=document.createElement('style');s.id='field-isolate';s.textContent="+json.dumps(css)+";document.head.append(s);return null})()"
 jobs.append({'name':name+'.png','rect':r,'script':script})
jobs.append({'name':'browser-base.png','rect':[431,129,610,390],'script':"document.getElementById('field-isolate')?.remove();document.querySelector('#kf-browse').click();document.querySelector('#krose-browser [role=list]').replaceChildren();(()=>{let s=document.createElement('style');s.textContent='#krose-browser input::placeholder{color:transparent!important}#krose-browser select{color:transparent!important}';document.head.append(s);return null})()"})
(p/'field-jobs.json').write_text(json.dumps(jobs))
