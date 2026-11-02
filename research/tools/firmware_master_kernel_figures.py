#!/usr/bin/env python3
"""Visualize exact stored window and explicitly conditional FIR behavior."""
import csv,json,math
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY,PALE
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def write_csv(path,rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def main():
    source=OUT/'master-kernel-check.json';d=json.loads(source.read_text());assert d['passed'] and d['actual_audio_algorithm_verified'] is False
    window=d['window'];host=d['host_reference'];assert len(window)==25 and len(d['factory'])==94
    c=Canvas(1200,930);c.text(600,14,'母带限制器：25 项窗与初始化地址',24)
    c.text(600,54,'原数据严格符合量化后的归一化 Hann 窗；七槽初始化与 94 个原厂槽位已核对。',14,GRAY)
    c.text(315,102,'已确认：原常数 1–25',19,BLUE);c.text(920,102,'主机候选：把这些数值用于 FIR',19,GOLD)
    left,right,top,bottom=90,550,160,375
    for value in [0,.04,.08]:
        y=bottom-(bottom-top)*value/.08;c.line(left,y,right,y,PALE);c.text(58,y-8,f'{value:.2f}',12,GRAY)
    c.line(left,top,left,bottom);c.line(left,bottom,right,bottom)
    for index,value in enumerate(host['weights']):
        x=left+(right-left)*index/24;y=bottom-(bottom-top)*value/.08;c.line(x,bottom,x,y,TEAL,3)
    for index in [0,6,12,18,24]:c.text(left+(right-left)*index/24,bottom+10,str(index),12,GRAY)
    c.text(315,421,'权重 = 原字 / 8388607；总和 = 1 − 8 / 8388607。',13,GRAY)
    left,right,top,bottom=710,1150,160,375
    for value in [0,.5,1]:
        y=bottom-(bottom-top)*value;c.line(left,y,right,y,PALE);c.text(680,y-8,f'{value:g}',12,GRAY)
    c.line(left,top,left,bottom);c.line(left,bottom,right,bottom)
    points=[(left+(right-left)*i/40,bottom-(bottom-top)*value) for i,value in enumerate(host['step'][:41])]
    for a,b in zip(points,points[1:]):c.line(*a,b[0],a[1],GOLD,2);c.line(b[0],a[1],*b,GOLD,2)
    for index in [0,12,24,40]:c.text(left+(right-left)*index/40,bottom+10,str(index),12,GRAY)
    c.text(920,421,'单位阶跃 / 帧序号；此曲线未执行原 TG 指令。',13,GRAY)
    c.text(600,487,'原初始化：两组端点差为 24，闭区间各含 25 个地址单元',20,BLUE)
    c.box(100,548,480,118,'常数 30 → 32',['base → base + 24','25 个地址单元'],TEAL)
    c.box(620,548,480,118,'常数 31 → 33',['base + 25 → base + 49','25 个地址单元'],BLUE)
    c.text(600,708,'25 项常数在 564 次原厂参数回调后保持原值；参数更新集中于阈值、上限、释放和干湿。',14,TEAL)
    c.text(600,754,'两个 MFX 槽位另外把程序项 108 / 110 / 112 / 113 的 C 字段改为 14；其算术含义尚未确定。',13,GRAY)
    c.text(600,801,'FIR 候选的群延迟为 12 帧。这是主机卷积的性质，琴的端到端延迟仍缺证据。',14,GOLD)
    c.text(600,845,'尚未确定：窗口用于检测、增益或音频的哪个环节；地址单位、读写顺序和 DSP 舍入。',13,GRAY)
    c.text(600,889,'已恢复数值与引用约束；完整母带限制器的音频算法继续保留缺口。',13,GRAY)
    c.save('master-limiter-window')
    weights=[dict(index=i,constant=i+1,word=value,analytic=d['analytic_window'][i],quantization_error=d['analytic_window'][i]-value,host_weight=host['weights'][i]) for i,value in enumerate(window)]
    curves=[dict(**row,magnitude_db=20*math.log10(max(row['magnitude'],1e-15))) for row in host['curves']]
    factory=[dict(program=row['program'],slot=row['slot'],source_sha256=row['source_sha256'],wet=row['parameters'][0],threshold=row['parameters'][3],ceiling=row['parameters'][4],release=row['parameters'][5],
        address30=row['constants'][30],address31=row['constants'][31],address32=row['constants'][32],address33=row['constants'][33],program_sha256=row['program_sha256']) for row in d['factory']]
    files=[OUT/'master-window-weights.csv',OUT/'master-window-reference-response.csv',OUT/'master-window-factory.csv']
    for path,rows in zip(files,[weights,curves,factory]):write_csv(path,rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},rows=[25,129,94],
        csv=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in files],
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/master-limiter-window.png',ROOT/'research/docs/architecture/figures/master-limiter-window.svg']])
    (OUT/'master-kernel-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered mastering-window figure and three inspectable CSV files.')
if __name__=='__main__':main()
