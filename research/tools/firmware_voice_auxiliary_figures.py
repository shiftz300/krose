#!/usr/bin/env python3
"""Visualize the tested omission boundary without implying full DSP equivalence."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    source=OUT/'voice-auxiliary-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    counts=d['counts'];assert counts['traces']==72 and counts['updates']==6912 and counts['commits']==3380
    c=Canvas(1040,620);c.text(520,16,'正常声部刷新：两段附加计算可以省略',24)
    c.text(520,58,'结论限于受测路径；保留其余原运算、全部演奏状态和 TG I/O 对照。',14,GRAY)
    c.box(45,115,400,90,'原管理器路径',['EG / LFO / Mixer → 音高与滤波目标'],BLUE)
    c.box(595,115,400,90,'省略后的插件路径',['相同原目标计算与批次顺序'],TEAL)
    c.box(45,250,400,110,'两段附加计算',['读取私有参数，更新 voice +1CC…+1EF','原绑定来源尚未确定'],GOLD)
    c.box(595,250,400,110,'直接进入后续计算',['不执行两段附加计算','不提供猜测的参数指针'],TEAL)
    c.box(45,405,400,85,'Amp / 声像 / TG 提交',['记录原寄存器写入与读回请求'],BLUE)
    c.box(595,405,400,85,'Amp / 声像 / TG 提交',['其余声部字节与原控制输出一致'],TEAL)
    for x in [245,795]:c.arrow(x,205,x,250);c.arrow(x,360,x,405)
    c.arrow(445,447,595,447,TEAL);c.text(520,419,'一致',14,TEAL)
    c.text(520,522,'72 条换音 / 踏板 / 批次轨迹 · 6912 次更新 · 3380 次 TG 控制提交',16,BLUE)
    c.text(520,559,'剩余轮询对附加区间的原指令读取：0；比较时仅排除这 36 字节。',14,GRAY)
    c.text(520,593,'未证明所有固件入口均可省略，也未验证 TG 音频、插值、滤波或芯片舍入。',13,GRAY)
    c.save('voice-auxiliary-omission')
    rows=[dict(old_bank=t['old'][0],old_program=t['old'][1],new_bank=t['new'][0],new_program=t['new'][1],batch=t['batch'],mode=t['mode'],pedal=t['pedal'],
        updates=len(t['steps']),commits=sum(len(s['commits']) for s in t['steps']),skipped_phase_entries=len(t['skipped']),outside_auxiliary_reads=len(t['outside_auxiliary_reads'])) for t in d['traces']]
    csvfile=OUT/'voice-auxiliary-traces.csv'
    with csvfile.open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},csv_sha256=sha(csvfile),rows=len(rows),
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/voice-auxiliary-omission.png',ROOT/'research/docs/architecture/figures/voice-auxiliary-omission.svg']])
    (OUT/'voice-auxiliary-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered auxiliary omission PNG/SVG and72-row CSV.')
if __name__=='__main__':main()
