#!/usr/bin/env python3
"""Locate Chorus control words in its native effect program."""
import csv,json
from pathlib import Path
from firmware_chorus import sha
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    source=OUT/'chorus-program-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    groups=[('速率',[3]),('波形选择',[4,5]),('左右相位差',[6]),('左右延迟基址',[1,2]),('左右预延迟',[7,8]),('调制深度',[9]),('前置 EQ 系数',list(range(13,19))),('湿声 / 干声',[11,12]),('公共相位偏移',[26])]
    c=Canvas(1120,750);c.text(560,12,'合唱控制字在原程序中的引用位置',24)
    c.text(560,52,'横轴为 0–105 的程序项编号；短线表示已核对的局部 A 字段，未解释音频读写关系',14,GRAY)
    left,right=300,1050;width=right-left;rows=[]
    for pc in [0,20,40,60,80,105]:
        x=left+pc/105*width;c.line(x,110,x,625,'#e5eef2');c.text(x,634,str(pc),12,GRAY)
    for line,(label,indices) in enumerate(groups):
        y=130+51*line;c.text(145,y-9,label,16,BLUE);c.line(left,y,right,y,'#cbd9e1')
        for index in indices:
            for pc in d['references'][index]['a_items']:
                x=left+pc/105*width;c.line(x,y-8,x,y+8,TEAL,3);rows.append(dict(group=label,kind='A',index=index,program_item=pc))
    y=589;c.text(145,y-9,'MFX 程序修正',16,GOLD);c.line(left,y,right,y,'#cbd9e1')
    for row in d['slots'][5]['mfx_modified']:
        pc=row['pc'];x=left+pc/105*width;c.line(x,y-9,x,y+9,GOLD,3);rows.append(dict(group='MFX 程序修正',kind='payload_edit',index='',program_item=pc))
    c.text(left+60.5/105*width,610,'59–62',12,GOLD)
    c.text(560,677,'波形参数 0 = Tri（三角波），1 = Sine（正弦波）；名称由原显示入口确认。',15,BLUE)
    c.text(560,714,'插值核、相位累加与延迟读写时序仍待确定；本图不提供完整合唱音频模型。',13,GRAY)
    c.save('chorus-program-references');dest=OUT/'chorus-program-references.csv'
    with dest.open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),csv_sha256=sha(dest),rows=len(rows),
        additional_helpers={'firmware_chorus.py':sha(ROOT/'research/tools/firmware_chorus.py')},
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/chorus-program-references.png',ROOT/'research/docs/architecture/figures/chorus-program-references.svg']])
    assert len(rows)==33
    (OUT/'chorus-program-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered Chorus control-reference PNG/SVG and 33-row CSV.')
if __name__=='__main__':main()
