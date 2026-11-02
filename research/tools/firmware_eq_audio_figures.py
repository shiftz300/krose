#!/usr/bin/env python3
"""Plot analytic cascade response against its executable host impulse FFT."""
import csv,json,math
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,GRAY,GOLD,PALE
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    source=OUT/'eq-audio-reference-check.json';d=json.loads(source.read_text());assert d['passed'] and len(d['curves'])==4
    c=Canvas(1180,820);c.text(590,16,'四段 EQ 级联：解析响应与实际主机运算',24)
    c.text(590,57,'原系数还原后组成参考级联；曲线包含原 Trim，B2 固定基础端点。',14,GRAY)
    all_db=[v for r in d['curves'] for v in r['analytic_db']];ymin=6*math.floor(min(all_db)/6);ymax=6*math.ceil(max(all_db)/6)
    for i,row in enumerate(d['curves']):
        x=95+(i%2)*565;y=170+(i//2)*282;w=450;h=190
        label=('低搁架' if row['low_shelf'] else '低频峰值')+' / '+('高搁架' if row['high_shelf'] else '高频峰值')
        c.text(x+w/2,y-59,f"{row['program']} {row['slot']} 参数：{label}",17,BLUE)
        def xx(f):return x+w*math.log(f/20)/math.log(1000)
        def yy(v):return y+h-h*(v-ymin)/(ymax-ymin)
        for value in range(ymin,ymax+1,6):c.line(x,yy(value),x+w,yy(value),PALE);c.text(x-28,yy(value)-7,str(value),12,GRAY)
        for f,label in [(20,'20'),(100,'100'),(1000,'1k'),(10000,'10k'),(20000,'20k')]:c.text(xx(f),y+h+10,label,12,GRAY)
        c.line(x,y,x,y+h);c.line(x,y+h,x+w,y+h);c.text(x-35,y-28,'dB',12,GRAY)
        points=[(xx(f),yy(db)) for f,db in zip(row['frequencies'],row['analytic_db'])]
        for a,b in zip(points,points[1:]):c.line(*a,*b,BLUE,2)
        for f,db in zip(row['frequencies'][::10],row['impulse_db'][::10]):
            a,b=xx(f),yy(db);c.line(a-3,b,a+3,b,GOLD,2);c.line(a,b-3,a,b+3,GOLD,2)
    c.line(300,697,345,697,BLUE,2);c.text(434,687,'解析级联',14,BLUE)
    c.line(680,697,695,697,GOLD,2);c.line(687,690,687,704,GOLD,2);c.text(804,687,'脉冲 FFT 取点',14,GOLD)
    c.text(590,737,'五组脉冲各 262144 帧，121 个频点；最大复数相对误差约 3.49e-11。',14,GRAY)
    c.text(590,774,'验证主机双精度实现；TG 动态混合、定点舍入与实际音色一致性仍待核对。',13,GRAY)
    c.save('eq-audio-reference')
    rows=[]
    for row in d['curves']:
        for f,a,b in zip(row['frequencies'],row['analytic_db'],row['impulse_db']):rows.append(dict(program=row['program'],slot=row['slot'],low_shelf=row['low_shelf'],high_shelf=row['high_shelf'],hz=f,analytic_db=a,impulse_db=b))
    csvfile=OUT/'eq-audio-reference-curves.csv'
    with csvfile.open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},csv_sha256=sha(csvfile),rows=len(rows),images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/eq-audio-reference.png',ROOT/'research/docs/architecture/figures/eq-audio-reference.svg']])
    (OUT/'eq-audio-reference-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered four-panel EQ reference and484-row CSV.')
if __name__=='__main__':main()
