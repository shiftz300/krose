#!/usr/bin/env python3
"""Draw the native-checked A000-to-A061 voice ownership example."""
import csv,hashlib,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    source=OUT/'midi-voice-handoff-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    trace=next(t for t in d['traces'] if t['old']==[0,0] and t['new']==[0,61] and t['mode']==3 and t['velocity']==127)
    assert trace['pool_unchanged_on_change'] and len(trace['first']['voices'])==4 and len(trace['second']['voices'])==1
    c=Canvas(1040,510);c.text(520,12,'换音前后的声部各自保留来源',24)
    c.text(520,52,'A000 双 OSC 钢琴 → A061 单 OSC Celesta；原 MIDI 连续流程，力度 127',14,GRAY)
    positions=[260,420,580,740,900]
    for x,title in zip(positions,['按键 48','换音','按键 64','松键 48','松键 64']):
        c.text(x,99,title,14,GOLD if title=='换音' else BLUE);c.line(x,127,x,414,'#dce5eb',1,True)
    rows=[]
    for i,(origin,event,color,start,end) in enumerate([('A000','first',BLUE,0,3)]*4+[('A061','second',TEAL,2,4)]):
        v=trace[event]['voices'][i if event=='first' else 0];y=160+48*i
        c.text(115,y-10,f"声部 {v['voice_slot']} / OSC {v['osc']+1}",14,color);c.text(115,y+10,f"{origin} / Sample {v['sample']}",11,GRAY)
        c.line(positions[start],y+4,positions[end],y+4,color,7)
        c.line(positions[end],y-7,positions[end],y+15,color,2)
        rows.append(dict(slot=v['voice_slot'],program=origin,osc=v['osc']+1,sample=v['sample'],note_on_event=start,note_off_event=end,program_pointer=v['program_pointer'],osc_pointer=v['osc_pointer']))
    c.text(520,435,'线段表示按键保持状态；竖线表示原关音处理，未按音频时长绘制。',13,GRAY)
    c.text(520,473,'旧 OSC2 退出新起音列表后，原关音入口仍会遍历它的旧声部。',14,GOLD);c.save('midi-voice-handoff')
    csvpath=OUT/'midi-voice-handoff-example.csv'
    with csvpath.open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),csv_sha256=sha(csvpath),example=dict(old=trace['old'],new=trace['new'],mode=3,velocity=127),rows=rows)
    (OUT/'midi-voice-handoff-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered MIDI handoff PNG/SVG and source-linked CSV.')
if __name__=='__main__':main()
