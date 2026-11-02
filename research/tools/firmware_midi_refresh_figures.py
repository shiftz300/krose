#!/usr/bin/env python3
"""Source-backed control trajectories for live MIDI Program changes."""
import csv,json,hashlib
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    source=OUT/'midi-voice-refresh-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    trace=next(t for t in d['traces'] if t['old']==[0,0] and t['new']==[0,61] and t['mode']==3 and t['batch']==8 and t['pedal'])
    rows=[]
    for s in trace['steps']:
        v={p['slot']:p for p in s['state']['voices']};row=dict(update=s['update'],channel_bend=s['state']['channel_bend'],timbre_bend=s['state']['timbre_bend'],
            volume=s['state']['volume'],expression=s['state']['controllers']['11'],pedal=s['state']['controllers']['64'])
        for slot in [0,2,4]:
            for key in ['amp','pitch']:row[f'voice{slot}_{key}']=v[slot][key] if slot in v else None
        rows.append(row)
    assert rows[12]['voice0_pitch']>rows[11]['voice0_pitch'] and rows[24]['voice0_pitch']==rows[11]['voice0_pitch']
    c=Canvas(1040,650);c.text(520,12,'换音后，旧声部继续响应公共控制',24)
    c.text(520,52,'A000 → A061 / 模式 3 / 批次 8 / 延音踏板；横轴为控制更新编号',14,GRAY)
    left,right=110,950;width=right-left
    for top,bottom,low,high,title,keys,colors in [(130,290,4500,5700,'旧钢琴声部 0：采样步进控制字',['voice0_pitch'],[BLUE]),
            (400,570,0,18000,'音量目标：旧钢琴与新 Celesta',['voice0_amp','voice2_amp','voice4_amp'],[BLUE,GOLD,TEAL])]:
        c.text(520,top-37,title,18,BLUE)
        for value in [low,(low+high)//2,high]:
            y=bottom-(value-low)/(high-low)*(bottom-top);c.line(left,y,right,y,'#e5eef2');c.text(left-42,y-7,str(value),12,GRAY)
        c.line(left,top,left,bottom);c.line(left,bottom,right,bottom)
        for value in [0,24,48,72,95]:c.text(left+value/95*width,bottom+10,str(value),12,GRAY)
        events=[(12,'弯音最大'),(24,'换音：弯音归零')] if top==130 else [(8,'CC7=99'),(40,'CC11=73'),(64,'松踏板')]
        for value,label in events:
            x=left+value/95*width;c.line(x,top,x,bottom,GRAY,1,True);c.text(x,top-18,label,12,GOLD)
        for key,color in zip(keys,colors):
            points=[(left+r['update']/95*width,bottom-(r[key]-low)/(high-low)*(bottom-top)) for r in rows if r[key] is not None]
            for p,q in zip(points,points[1:]):c.line(*p,*q,color,2)
    for x,label,color in [(240,'旧声部 0 / OSC1',BLUE),(510,'旧声部 2 / OSC2',GOLD),(790,'新声部 4 / Celesta',TEAL)]:
        c.line(x-80,612,x-45,612,color,3);c.text(x+35,603,label,13,color)
    c.text(520,631,'图中为原控制目标，未绘制 DSP 音频，也未将更新编号换算为毫秒。',12,GRAY);c.save('midi-voice-refresh')
    dest=OUT/'midi-voice-refresh-example.csv'
    with dest.open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    data=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),csv_sha256=sha(dest),rows=len(rows),
              example=dict(old=trace['old'],new=trace['new'],mode=3,batch=8,pedal=True),images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/midi-voice-refresh.png',ROOT/'research/docs/architecture/figures/midi-voice-refresh.svg']])
    (OUT/'midi-voice-refresh-figure-check.json').write_text(json.dumps(data,indent=2)+'\n');print('Rendered live MIDI refresh PNG/SVG and96-row CSV.')
if __name__=='__main__':main()
