#!/usr/bin/env python3
"""Draw the PPAT-to-voice path and export the measured control traces."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY,PALE
from firmware_midi_program_load import sha
from firmware_voice_lfo import OUT
from layout import PRODUCT_ROOT as ROOT

def exports(d):
    events=[];voices=[];steps=[]
    for t in d['traces']:
        context={k:t[k] for k in ['program','pattern','synthetic','batch']}
        events.extend(dict(**context,**r) for r in t['dispatched'])
        voices.extend(dict(**context,**{k:v for k,v in r.items() if k!='sample_registers'},sample_registers=json.dumps(r.get('sample_registers',{}),sort_keys=True)) for r in t['constructed'])
        steps.extend(dict(**context,**r) for r in t['steps'])
    return events,voices,steps

def main():
    source=OUT/'drum-voice-playback-check.json';d=json.loads(source.read_text())
    assert d['passed'] and not d['smoke_only'] and not d['actual_DSP_audio_executed']
    c=Canvas(1200,820);c.text(600,15,'鼓轨事件进入真实声部',25)
    c.text(600,58,'同一原 ARM 内存：PPAT 播放 → 本机 MIDI 输入 → 鼓组选层与起音 → 正常控制刷新',15,GRAY)
    cells=[(45,'原 PPAT 轨道',['原厂 31 / 799 与两圈合成轨','绑定、tick、延音表与停止']),
           (445,'本机 MIDI 输入',['2BD7B4 → 271500','通道 7，事件来源 1']),
           (845,'真实鼓组声部',['F033 立体声 / F042 单声道','采样、增益与启动地址逐项核对'])]
    for x,title,lines in cells:c.box(x,110,310,112,title,lines,BLUE)
    c.arrow(355,166,445,166);c.arrow(755,166,845,166)
    c.box(245,266,710,98,'正常声部管理器：批次 4 / 16，每 8 个音乐 tick 推进与轮询',
          ['完整软件状态与 TG I/O 对照显式原函数调度；受控读回，未执行 DSP 音频'],TEAL)
    c.arrow(1000,222,1000,246);c.arrow(1000,246,840,266)
    c.text(600,405,'合成轨两圈：循环首音出现在 tick 1921；长音在圈末关断',19)
    c.text(600,435,'蓝色端点：起音；金色端点：关音；绿色线段：事件持续区间',12,GRAY)
    left,right=140,1110
    for tick in [0,960,1920,2880,3840]:
        x=left+tick/3840*(right-left);c.line(x,455,x,632,PALE);c.text(x,645,str(tick),12,GRAY)
    row=next(t for t in d['traces'] if t['synthetic'] and t['program']=='F042' and t['batch']==16)
    for n,y in [(36,475),(38,535),(42,595)]:
        c.text(70,y-10,f'键 {n}',14,GRAY);c.line(left,y,right,y,PALE)
        pending=[]
        for e in row['music_events']:
            if e['note']!=n:continue
            x=left+e['tick']/3840*(right-left)
            if e['status']&240==144:pending.append((x,e['tick']))
            else:
                start,tick=pending.pop(0);c.line(start,y,x,y,TEAL,4)
                c.line(start,y-8,start,y+8,BLUE,2);c.line(x,y-8,x,y+8,GOLD,2)
                if n==42:c.text((start+x)/2,y-27,f'{tick}–{e["tick"]}',12,GRAY)
        assert not pending
    c.text(600,689,'横轴为音乐 tick；线段表示生成事件的起音到关音，不表示实际声音长度。',14,GRAY)
    q=d['counts'];c.text(600,733,f'{q["traces"]} 条轨迹 · {q["updates"]} 次控制更新 · {q["voices"]} 个声部 · {q["commits"]} 次提交',16,TEAL)
    c.text(600,775,'TG 启停与零幅度目标即时应答；其余幅度固定。宿主时基与芯片音频仍待验证。',14,GOLD)
    c.save('drum-voice-playback')
    rows=exports(d);paths=[OUT/('drum-voice-playback-'+name+'.csv') for name in ['events','voices','updates']]
    for path,data in zip(paths,rows):
        with path.open('w',newline='') as stream:
            w=csv.DictWriter(stream,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_midi_program_load.py','firmware_voice_lfo.py']},
        rows=list(map(len,rows)),csv=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in paths],
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures'/('drum-voice-playback.'+ext) for ext in ['png','svg']]])
    (OUT/'drum-voice-playback-figure-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,rows=result['rows'])))
if __name__=='__main__':main()
