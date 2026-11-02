#!/usr/bin/env python3
"""Plot original drum EG levels under early/late edits; export actual states."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY,PALE
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    source=OUT/'drum-eg-live-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    c=Canvas(1200,840);c.text(600,16,'鼓声中的参数编辑：当前段与后续段分别读取',24)
    c.text(600,57,'F042 / Basic Kit 1 · 键 48 · 批量 8；只画第一次起音的原包络控制电平。',14,GRAY)
    traces={v:next(t for t in d['traces'] if (t['program'],t['batch'],t['variant'])==('F042',8,v)) for v in ['early','late']}
    for panel,variant in enumerate(['early','late']):
        t=traces[variant];voice=t['first_voices'][0];left=90+600*panel;right=540+600*panel;top=160;bottom=405
        c.text((left+right)/2,109,'早改：起音后，Decay 尚未开始' if variant=='early' else '晚改：音量 Decay 已开始',19,BLUE)
        for value in [0,.5,1]:
            y=bottom-(bottom-top)*value;c.line(left,y,right,y,PALE);c.text(left-27,y-8,str(value),12,GRAY)
        c.line(left,top,left,bottom);c.line(left,bottom,right,bottom)
        for index,color in [(0,BLUE),(1,TEAL)]:
            previous=None
            for step in t['steps'][:256]:
                state=next((v for v in step['state'] if v['voice']==voice),None)
                if state is None:previous=None;continue
                point=(left+(right-left)*step['update']/255,bottom-(bottom-top)*state['levels'][index]/32767)
                if previous is not None:c.line(*previous,*point,color,2)
                previous=point
        for update in [0,64,128,192,255]:c.text(left+(right-left)*update/255,bottom+12,str(update),12,GRAY)
        c.text((left+right)/2,bottom+42,'管理器更新序号（受控调度，未换算毫秒）',13,GRAY)
        edit=next(e for e in t['key_edits'] if e['selector']==23)
        x=left+(right-left)*edit['update']/255;c.line(x,top,x,bottom,GOLD,1,True)
        c.text((left+right)/2,466,f"Decay 写入 {edit['value']}，更新 {edit['update']}；当前 EG 字节保持原值。",13,GOLD)
        if variant=='early':
            stop=next(s['update'] for s in t['steps'] if not any(v['voice']==voice for v in s['state']))
            c.text((left+right)/2,499,f'旧声部在更新 {stop} 回收；滤波尚未进入 Decay。',13,GRAY)
        else:
            transition=next(o for o in t['offsets'] if o['voice']==voice and o['kind']=='filter' and o['phase']=='decay')
            c.text((left+right)/2,499,f"滤波在更新 {transition['update']} 进入 Decay，读取新值 32。",13,GRAY)
    c.line(350,550,384,550,BLUE,3);c.text(437,540,'Filter EG',14,BLUE)
    c.line(650,550,684,550,TEAL,3);c.text(735,540,'Amp EG',14,TEAL)
    c.box(70,592,495,108,'旧音符的当前段',['已建立的时间与曲线继续推进','原逐键写入不立即重算当前段'],TEAL)
    c.box(635,592,495,108,'后续阶段与再次起音',['建立段时读取届时的逐键值','旧声部与新声部可以采用不同时间'],BLUE)
    c.text(600,734,f"{d['counts']['traces']} 条轨迹 · {d['counts']['updates']} 次更新 · {d['counts']['core_steps']} 次原核心推进逐字节核对",15,TEAL)
    c.text(600,777,'曲线为原控制电平，不代表音频波形；TG 启停响应、时钟与读回由验证环境提供。',13,GRAY)
    c.save('drum-eg-live')
    rows=[]
    for number,t in enumerate(d['traces']):
        for step in t['steps']:
            for v in step['state']:
                rows.append(dict(trace=number,program=t['program'],note=t['note'],batch=t['batch'],variant=t['variant'],update=step['update'],voice=v['voice'],pair=v['pair'],
                    filter_stage=v['stages'][0],amp_stage=v['stages'][1],filter_level=v['levels'][0],amp_level=v['levels'][1],
                    filter_remaining=v['remaining'][0],amp_remaining=v['remaining'][1],filter_duration=v['durations'][0],amp_duration=v['durations'][1]))
    path=OUT/'drum-eg-live-states.csv'
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},rows=len(rows),csv=dict(path=str(path.relative_to(ROOT)),sha256=sha(path)),
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/drum-eg-live.png',ROOT/'research/docs/architecture/figures/drum-eg-live.svg']])
    (OUT/'drum-eg-live-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,rows=len(rows))))
if __name__=='__main__':main()
