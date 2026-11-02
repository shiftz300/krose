#!/usr/bin/env python3
"""Native drum EG time indices and explicit stage-consumption boundary."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD,PALE
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    source=OUT/'drum-eg-times-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    c=Canvas(1200,810);c.text(600,16,'鼓组逐键 Attack / Decay：阶段入口读取时间修正',24)
    c.text(600,57,'F042 / Basic Kit 1 · 键 48 · 力度 100；纵轴为内部时间索引，未换算毫秒。',14,GRAY)
    baseline=next(t for t in d['traces'] if t['program']=='F042' and t['key_attack']==t['key_decay']==64)
    voice=baseline['voices'][0]
    for panel,phase in enumerate(['attack','decay']):
        left=90+600*panel;right=540+600*panel;top=165;bottom=395
        c.text((left+right)/2,111,'Attack（选择器 22）' if panel==0 else 'Decay（选择器 23）',19,BLUE)
        for value in [0,50,99]:
            y=bottom-(bottom-top)*value/99;c.line(left,y,right,y,PALE);c.text(left-25,y-8,str(value),12,GRAY)
        c.line(left,top,left,bottom);c.line(left,bottom,right,bottom)
        for kind,color in [('filter',BLUE),('amp',TEAL)]:
            row=next(o for o in baseline['offsets'] if (o['voice'],o['kind'],o['phase'])==(voice,kind,phase))
            points=[]
            for key in range(128):
                time=max(0,min(99,row['shared_base']+row['layer']+key-64))
                points.append((left+(right-left)*key/127,bottom-(bottom-top)*time/99))
            for a,b in zip(points,points[1:]):c.line(*a,*b,color,2)
            for key in [0,64,127]:
                t=next(t for t in d['traces'] if t['program']=='F042' and t['key_attack']==(key if phase=='attack' else 64) and t['key_decay']==(key if phase=='decay' else 64))
                s=next(s for s in t['segments'] if (s['voice'],s['kind'],s['phase'])==(voice,kind,phase))
                x=left+(right-left)*key/127;y=bottom-(bottom-top)*s['time_index']/99
                c.line(x-4,y-4,x+4,y+4,color,2);c.line(x-4,y+4,x+4,y-4,color,2)
        for key in [0,64,127]:c.text(left+(right-left)*key/127,bottom+12,str(key),12,GRAY)
        c.text((left+right)/2,bottom+42,'逐键控制值（64 为中性值）',13,GRAY)
    c.line(340,470,374,470,BLUE,3);c.text(422,460,'滤波 EG',14,BLUE)
    c.line(650,470,684,470,TEAL,3);c.text(730,460,'音量 EG',14,TEAL)
    c.text(600,505,'曲线由已核对公式计算；× 为三组原厂阶段入口的实际结果。',13,GRAY)
    c.box(65,553,310,100,'原逐键写入',['保存新控制值','当前 EG 状态字节保持原值'],BLUE)
    c.box(445,553,310,100,'进入 Attack / Decay',['读取共享基值、层修正与逐键值','相加并限制到 0–99'],TEAL)
    c.box(825,553,310,100,'建立新的包络段',['查原时间表，应用时间 AMS','时长与曲线状态逐字节核对'],BLUE)
    c.arrow(375,603,445,603);c.arrow(755,603,825,603)
    c.text(600,690,'42 套鼓组代表键 · 378 组设置 · 2052 次修正 · 4104 次阶段时间建立',15,TEAL)
    c.text(600,729,'受测 Slope / Release 时间索引保持原值；本项显式调用阶段入口，未验证自然连续推进。',13,GOLD)
    c.text(600,769,'未执行 TG 音频；其他编辑回调及宿主连续演奏仍需独立验收。',13,GRAY)
    c.save('drum-eg-time-offsets')
    rows=[dict(program=t['program'],note=t['note'],key_attack=t['key_attack'],key_decay=t['key_decay'],**s) for t in d['traces'] for s in t['segments']]
    path=OUT/'drum-eg-time-segments.csv'
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},
        rows=len(rows),csv=dict(path=str(path.relative_to(ROOT)),sha256=sha(path)),
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/drum-eg-time-offsets.png',ROOT/'research/docs/architecture/figures/drum-eg-time-offsets.svg']])
    (OUT/'drum-eg-times-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,rows=len(rows))))
if __name__=='__main__':main()
