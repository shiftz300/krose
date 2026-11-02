#!/usr/bin/env python3
"""Show verified all-off behavior and preserve stereo-reuse failures."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    source=OUT/'midi-all-off-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only'] and not d['live_continuity_complete']
    rows=[]
    for controller in [123,120]:
        t=next(t for t in d['live'] if t['old']==[0,0] and t['new']==[0,61] and t['mode']==3 and t['pedals']==3 and t['controller']==controller)
        event=t['steps'][0]['event']['off'];rows.append(dict(controller=controller,before=len(event['before']),after=len(event['after']),released=len(event['released']),killed=len(event['killed']),
            available=event['available'],channel_preserved=event['channel_preserved'],reuse_fault_update=t['reuse_fault']['update']))
    assert [(r['before'],r['after'],r['released'],r['killed']) for r in rows]==[(5,5,1,0),(5,0,0,5)]
    c=Canvas(1040,660);c.text(520,12,'CC123 与 CC120：释音和硬停的区别',24)
    c.text(520,52,'A000 → A061 / 模式 3 / 两踏板开启；原关音调用返回时的声部数',14,GRAY)
    for x,row,title in [(45,rows[0],'CC123 / All Notes Off'),(555,rows[1],'CC120 / All Sound Off')]:
        c.box(x,108,440,190,title,[f"调用前：{row['before']} 个声部",f"调用后仍分配：{row['after']} 个",f"释放请求：{row['released']}；硬停回收：{row['killed']}",f"空闲槽：{row['available']} / 32"],BLUE if row['controller']==123 else TEAL)
    c.text(520,328,'两条命令都保留控制器；CC123 继续遵守踏板和鼓键释放规则。',16,BLUE)
    c.text(520,380,'后续复用仍有失败证据',20,GOLD)
    c.box(45,431,260,92,'硬停回收', ['成对声部移出活动列表'],GOLD)
    c.box(390,431,260,92,'重新申请声部',['旧配对引用仍在'],GOLD)
    c.box(735,431,260,92,'移除伙伴节点',['节点已清空，访问地址 0x4'],GOLD)
    c.arrow(305,478,390,478,GOLD);c.arrow(650,478,735,478,GOLD)
    c.text(520,564,'原 MIDI 调度与显式原函数调度均复现；尚不能据此认定实机故障。',14,GOLD)
    c.text(520,609,'已核对关音规则；停止后的完整连续演奏未通过。本图没有绘制 DSP 音频。',13,GRAY)
    c.save('midi-all-off-behavior')
    csvfile=OUT/'midi-all-off-example.csv'
    with csvfile.open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    faults=[]
    for t in d['live']:
        f=t['reuse_fault']
        if f:faults.append(dict(old_bank=t['old'][0],old_program=t['old'][1],new_bank=t['new'][0],new_program=t['new'][1],controller=t['controller'],mode=t['mode'],pedals=t['pedals'],update=f['update'],pc=f['memory_fault']['pc'],address=f['memory_fault']['address'],unlinked_index=f['unlinked']['unlinked_index']))
    faultfile=OUT/'midi-all-off-reuse-faults.csv'
    with faultfile.open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(faults[0]));w.writeheader();w.writerows(faults)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},
        csv_sha256=sha(csvfile),rows=len(rows),fault_csv_sha256=sha(faultfile),fault_rows=len(faults),
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/midi-all-off-behavior.png',ROOT/'research/docs/architecture/figures/midi-all-off-behavior.svg']])
    (OUT/'midi-all-off-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered all-off behavior PNG/SVG and evidence CSVs.')
if __name__=='__main__':main()
