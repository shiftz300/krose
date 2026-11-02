#!/usr/bin/env python3
"""Show occupancy and paired replacement in the120-slot native study."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY,PALE
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
LABELS={(0,0):'A000 钢琴',(0,11):'A011 钢琴叠层',(0,61):'A061 Celesta',(20,0):'GM 标准鼓组'}

def main():
    source=OUT/'voice-pressure-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    assert d['counts']['traces']==32 and d['counts']['updates']==5632
    c=Canvas(1180,900);c.text(590,14,'声部耗尽后继续弹奏：120 槽连续验证',24)
    c.text(590,54,'每条连续起音 144 次，再松键、松踏板、强停和重新起音；共 32 条轨迹。',14,GRAY)
    left,right,top,bottom=105,1100,145,445
    for y in [0,30,60,90,120]:
        pos=bottom-(bottom-top)*y/120;c.line(left,pos,right,pos,PALE);c.text(75,pos-9,str(y),13,GRAY)
    for x in [0,24,48,72,96,120,143]:c.text(left+(right-left)*x/143,bottom+9,str(x),12,GRAY)
    c.line(left,top,left,bottom);c.line(left,bottom,right,bottom);c.text(98,112,'占用槽数',13,GRAY)
    for k,((preset,label),color) in enumerate(zip(LABELS.items(),[BLUE,TEAL,GOLD,GRAY])):
        trace=next(t for t in d['traces'] if tuple(t['preset'])==preset and t['batch']==8 and t['pedal'] and t['score_profile']=='equal')
        points=[(left+(right-left)*s['update']/143,bottom-(bottom-top)*len(s['state']['active_slots'])/120) for s in trace['steps'][:144]]
        for a,b in zip(points,points[1:]):c.line(*a,b[0],a[1],color,2);c.line(b[0],a[1],*b,color,2)
        x=190+265*k;c.line(x-60,92,x-35,92,color,3);c.text(x+25,82,label,14,color)
    c.text(590,484,'连续起音序号（非实测时间）；上图取批量 8、延音开启、评分读回固定。',13,GRAY)
    c.text(590,531,'同一池中的实际抢占与回收',20,BLUE)
    headers=[(175,'音色'),(435,'首次用满序号'),(700,'活动声部抢占'),(1000,'其中成对抢占')]
    for x,label in headers:c.text(x,578,label,15,BLUE)
    summaries=[]
    for i,(preset,label) in enumerate(LABELS.items()):
        traces=[t for t in d['traces'] if tuple(t['preset'])==preset];assert len(traces)==8
        representative=next(t for t in traces if t['batch']==8 and t['pedal'] and t['score_profile']=='equal')
        first=next((s['update'] for s in representative['steps'][:144] if s['state']['available']==0),None)
        active=sum(row['was_active'] for t in traces for row in t['reclaims'])
        paired=sum(row['was_active'] and row['pair']!=0 for t in traces for row in t['reclaims'])
        y=624+40*i;c.line(65,y+31,1115,y+31,PALE)
        for x,val in zip([175,435,700,1000],[label,str(first) if first is not None else '本序列未用满',str(active),str(paired)]):c.text(x,y,val,15,TEAL if x>435 else BLUE)
        summaries.append(dict(preset=list(preset),first_full_update=first,active_reclaims=active,paired_active_reclaims=paired))
    compare_traces=[next(t for t in d['traces'] if t['preset']==[0,0] and t['batch']==8 and not t['pedal'] and t['score_profile']==profile) for profile in ['equal','varied']]
    sequences=[[r['selected_slot'] for r in t['selections'] if r['selected_slot'] is not None] for t in compare_traces]
    assert len(sequences[0])==len(sequences[1]);different=sum(a!=b for a,b in zip(*sequences))
    c.text(590,802,f'A000、批量 8：更换评分读回后，{different}/{len(sequences[0])} 次非空候选选择改变；表中抢占合计 8 条轨迹。',13,GRAY)
    c.text(590,837,'停止完成采用受控即时响应；评分含义、硬件延迟、实际音频和 Mono/Unison 仍待确认。',13,GRAY)
    c.text(590,871,'逐事件、推进、轮询比较完整状态与 TG I/O；候选顺序和评分另由独立规则核对。',13,GRAY)
    c.save('voice-pressure')
    rows=[]
    for index,t in enumerate(d['traces']):
        for s in t['steps']:
            state=s['state'];lo,hi=s['reclaim_range'];reclaims=t['reclaims'][lo:hi]
            rows.append(dict(trace=index,preset=LABELS[tuple(t['preset'])],batch=t['batch'],pedal=t['pedal'],score_profile=t['score_profile'],
                update=s['update'],allocated=len(state['active_slots']),key_on=len(state['key_on_slots']),available=state['available'],
                note=s['event'].get('note',{}).get('note'),initialized=len(s['event'].get('note',{}).get('voices',[])),
                selection_calls=s['selection_range'][1]-s['selection_range'][0],active_reclaims=sum(r['was_active'] for r in reclaims),commits=len(s['commits'])))
    csvpath=OUT/'voice-pressure-updates.csv'
    with csvpath.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    assert len(rows)==5632
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},rows=len(rows),csv_sha256=sha(csvpath),summaries=summaries,
        A000_score_comparison=dict(batch=8,pedal=False,nonempty_selections=len(sequences[0]),different_selections=different),
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/voice-pressure.png',ROOT/'research/docs/architecture/figures/voice-pressure.svg']])
    (OUT/'voice-pressure-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(rows=len(rows),summaries=summaries)))
if __name__=='__main__':main()
