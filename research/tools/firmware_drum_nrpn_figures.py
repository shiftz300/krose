#!/usr/bin/env python3
"""Inspect the native NRPN selector-retention trace and export every CC."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def write_csv(path,rows):
    with path.open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    source=OUT/'drum-nrpn-live-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    c=Canvas(1200,840);c.text(600,16,'NRPN 到鼓组包络：选择状态会保留',24)
    c.text(600,57,'原 MIDI 控制器事件 → 通道 7 → 逐键记录 → 正常包络推进；串口字节收发不在此范围。',14,GRAY)
    for x,title,lines,color in [(65,'CC99：参数高字节',['22 = Attack / 23 = Decay','只改变高字节时，旧键号可继续使用'],BLUE),
        (445,'CC98：鼓键低字节',['0–127，选择目标鼓键','只改变键号时，旧参数号仍有效'],TEAL),
        (825,'CC6：参数值',['按当前选择状态解释','逐键写入，留给阶段入口读取'],BLUE)]:c.box(x,110,310,108,title,lines,color)
    c.arrow(375,164,445,164);c.arrow(755,164,825,164)
    rows=[('99:22 → 98:48 → 6:70','键 48 / Attack = 70',BLUE),
          ('99:23 → 6:41','键 48 / Decay = 41（沿用键号）',TEAL),
          ('98:49 → 6:42','键 49 / Decay = 42（沿用参数号）',TEAL),
          ('101:127 → 100:127 → 6:99','Null RPN：逐键记录保持原值',GRAY),
          ('99:22 → 6:43','键 49 / Attack = 43（切回后仍沿用键号）',GOLD)]
    for i,(sequence,result,color) in enumerate(rows):
        y=265+59*i;c.text(305,y,sequence,17,color);c.arrow(555,y+12,625,y+12,color);c.text(890,y,result,16,color)
    c.text(600,589,'上表来自原分发入口的连续事件；不能在每次选择后自动清空另一半状态。',14,GOLD)
    c.box(65,637,495,102,'消息来源 5',['活动控制与逐键参数照常更新','通道影子值保持原值'],TEAL)
    c.box(640,637,495,102,'受测连续包络',['来源 0 / 5 的六组配对结果一致','保留当前段，后续阶段读取新值'],BLUE)
    c.text(600,775,f"{d['counts']['matrix_messages']} 条边界消息 · {d['counts']['traces']} 条演奏轨迹 · {d['counts']['updates']} 次正常更新；未执行 TG 音频。",14,GRAY)
    c.save('drum-nrpn-state')
    def flat(row,group,trace):
        return dict(group=group,trace=trace,update=row['update'],cc=row['cc'],value=row['value'],source=row['source'],flags=row['flags'],
            selected_high=row['selected_high'],selected_key=row['selected_key'],live=row['live'],shadow=row['shadow'],keys_sha256=row['keys_sha256'],
            changes=json.dumps(row['changes'],sort_keys=True,separators=(',',':')))
    matrix=[flat(row,group,-1) for group,rows in d['matrix'].items() for row in rows]
    live=[flat(row,'live',i) for i,t in enumerate(d['traces']) for row in t['messages']]
    paths=[OUT/'drum-nrpn-messages.csv',OUT/'drum-nrpn-live-messages.csv']
    for path,rows in zip(paths,[matrix,live]):write_csv(path,rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},rows=[len(matrix),len(live)],
        csv=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in paths],
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/drum-nrpn-state.png',ROOT/'research/docs/architecture/figures/drum-nrpn-state.svg']])
    (OUT/'drum-nrpn-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,rows=result['rows'])))
if __name__=='__main__':main()
