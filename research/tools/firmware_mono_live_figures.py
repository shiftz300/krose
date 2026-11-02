#!/usr/bin/env python3
"""Plot verified key priority and real voice reuse across mono modes."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY,PALE
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
PRESETS=[([3,24],'D024 普通单音'),([3,9],'D009 Normal 连奏'),([3,46],'D046 Offset 连奏'),
         ([3,17],'D017 Unison 2'),([3,15],'D015 Unison 3'),([5,6],'F006 Unison 4'),([5,110],'F110 Unison 6')]
def main():
    source=OUT/'mono-live-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    assert d['counts']['traces']==26 and d['counts']['updates']==4160
    c=Canvas(1180,1040);c.text(590,14,'单音与连奏：按键回退接入真实声部',24)
    c.text(590,54,f"26 条轨迹 / 4160 次更新 / {d['counts']['retunes']} 次原复用调音；按键表、采样与控制状态逐阶段核对。",14,GRAY)
    left,right,top,bottom=110,1090,145,365
    for note in [60,62,64]:
        y=bottom-(bottom-top)*(note-60)/4;c.line(left,y,right,y,PALE);c.text(78,y-9,str(note),13,GRAY)
    c.line(left,top,left,bottom);c.line(left,bottom,right,bottom);c.text(95,109,'当前按键',13,GRAY)
    for priority,color,label in [(0,BLUE,'Low'),(1,TEAL,'High'),(2,GOLD,'Last')]:
        t=next(t for t in d['traces'] if t['preset']==[3,9] and t['priority']==priority and t['pedal'])
        values=[t['steps'][i]['event']['keys'][0] for i in [0,4,8,12,16]]
        points=[(left+(right-left)*i/20,bottom-(bottom-top)*(note-60)/4) for i,note in zip([0,4,8,12,16],values)]
        for a,b in zip(points,points[1:]):c.line(*a,b[0],a[1],color,2);c.line(b[0],a[1],*b,color,2)
        x=320+270*priority;c.line(x-45,94,x-20,94,color,3);c.text(x+30,84,label,14,color)
        assert not t['steps'][20]['event']['keys']
    for i,label in zip([0,4,8,12,16,20],['On 60/40','On 64/80','On 62/100','Off 62','Off 64','Off 60']):
        x=left+(right-left)*i/20;c.text(x,bottom+15,label,13,GRAY)
    c.text(1090,301,'空表',13,GRAY)
    c.text(590,421,'横轴为更新序号；末尾松键后按键表为空。所有模式均继续执行原采样与正常轮询。',13,GRAY)
    c.text(590,473,'同一组演奏输入，不同单音模式的声部行为',20,BLUE)
    for x,label in [(230,'原厂 Program'),(590,'新建声部'),(820,'复用调音'),(1060,'采样 / EG 保留')]:c.text(x,522,label,15,BLUE)
    summaries=[]
    for i,(preset,label) in enumerate(PRESETS):
        trace=next(t for t in d['traces'] if t['preset']==preset and t['priority']==2 and t['pedal'])
        created=sum(len(s['event']['created']) for s in trace['steps']);retunes=sum(len(s['event']['retunes']) for s in trace['steps'])
        y=566+43*i
        for x,value in [(230,label),(590,str(created)),(820,str(retunes)),(1060,'逐次通过' if retunes else '-')]:c.text(x,y,value,15,TEAL if x>400 else BLUE)
        c.line(70,y+32,1110,y+32,PALE);summaries.append(dict(preset=preset,created=created,retunes=retunes))
    example=next(t for t in d['traces'] if t['preset']==[3,9] and t['priority']==2 and t['pedal'])
    retained=[row for step in [4,8] for row in example['steps'][step]['event']['retunes']]
    assert retained and all(r['velocity_before']==r['velocity_after']==40 for r in retained)
    c.text(590,902,'D009 输入 64/80、62/100 时，复用声部保留力度 40；采样、EG 与 LFO 均保持原状态。',14,TEAL)
    c.text(590,946,'表中取 Last 与延音开启；新建和调音均为槽次数。Low/High 仅覆盖记录的私有优先级位。',13,GRAY)
    c.text(590,987,'TG 使用受控读回及启动 / 停止响应；横轴未换算实机时间，尚未验证实际声音。',13,GRAY)
    c.save('mono-live')
    rows=[]
    for index,t in enumerate(d['traces']):
        for s in t['steps']:
            event=s['event'];rows.append(dict(trace=index,bank=t['preset'][0],program=t['preset'][1],priority=t['priority'],pedal=t['pedal'],
                update=s['update'],input=json.dumps(event['input']),keys=json.dumps(event['keys']),cached_velocity=event['cached_velocity'],pressed_count=event['count'],
                created=len(event['created']),retunes=len(event['retunes']),allocated=len(s['state']['voices']),available=s['state']['available'],commits=len(s['commits'])))
    csvpath=OUT/'mono-live-updates.csv'
    with csvpath.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    assert len(rows)==4160
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},rows=len(rows),csv_sha256=sha(csvpath),summaries=summaries,
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/mono-live.png',ROOT/'research/docs/architecture/figures/mono-live.svg']])
    (OUT/'mono-live-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(rows=len(rows),summaries=summaries)))
if __name__=='__main__':main()
