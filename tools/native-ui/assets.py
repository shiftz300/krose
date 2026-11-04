"""Generate transparent native assets from the approved page. Authoring only."""
import json, math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
out = ROOT / 'build/native-ui'
layout = json.loads((out / 'layout.json').read_text())
jobs, assets = [], []
def capture(name, selector, rect, script='', extra=''):
    css = ('html,body,#krose-fixed-ui .instrument{background:transparent!important;box-shadow:none!important;border-color:transparent!important}'
           '#krose-fixed-ui .instrument *{visibility:hidden!important}'
           '#krose-fixed-ui .instrument ' + selector + '{visibility:visible!important}'
           '#krose-fixed-ui .instrument ' + selector + ' *{visibility:visible!important}' + extra)
    setup = "(()=>{let s=document.getElementById('native-isolate');if(!s){s=document.createElement('style');s.id='native-isolate';document.head.append(s)}s.textContent=" + json.dumps(css) + ";" + script + ";return null})()"
    jobs.append({'name': name + '.png', 'script': setup, 'rect': rect})
    assets.append({'name': name, 'selector': selector, 'rect': rect})
# A separate pointer allows continuous native rotation without a stepped filmstrip.
capture('knob-shell', '[data-control=glide] .knob', [143,168,64,64], extra='#krose-fixed-ui .instrument [data-control=glide] .knob .pointer{visibility:hidden!important}')
capture('knob-pointer', '[data-control=glide] .pointer', [151,176,48,48], "document.querySelector('[data-control=glide] .knob').style.setProperty('--angle','0deg')")
for e in layout['elements']:
    if e['tag'] != 'BUTTON' or 'switch' not in e['classes']:
        continue
    data = next(((k,v) for k,v in e['data'].items() if k in ('toggle','eg','voice')), None)
    selector = '#' + e['id'] if e['id'] else '[data-' + data[0] + '=' + data[1] + ']'
    name = e['id'] or data[1]
    x,y,w,h = e['rect']
    rect = [math.floor(x)-3, math.floor(y)-3, math.ceil(x+w)-math.floor(x)+6, math.ceil(y+h)-math.floor(y)+6]
    for pressed in (False, True):
        capture('button-' + name + ('-on' if pressed else '-off'), selector, rect,
                'document.querySelector(' + json.dumps(selector) + ").setAttribute('aria-pressed','" + str(pressed).lower() + "')")
reset = "document.getElementById('native-isolate')?.remove();window.kroseNative.receive('Program',5,1);document.querySelector('.lcd-tab[data-page=main]').click();"
hide = "(()=>{const s=document.createElement('style');s.id='native-materials';s.textContent='#krose-fixed-ui .knob,#krose-fixed-ui .readout,#krose-fixed-ui .fader input,#krose-fixed-ui .fader output,#krose-fixed-ui .wheel-mark,#krose-fixed-ui .switch,#krose-fixed-ui .lcd>*,#kf-program,#krose-fixed-ui .keyboard button,#krose-fixed-ui .octaves{visibility:hidden!important}';document.head.append(s)})();"
jobs.append({'name':'material-expanded.png','script':reset+hide})
jobs.append({'name':'material-folded.png','script':"document.querySelector('.fx-lettering').click()"})
(out/'asset-jobs.json').write_text(json.dumps(jobs))
(out/'asset-index.json').write_text(json.dumps(assets,indent=2)+'\n')
print(len(jobs), 'captures')
