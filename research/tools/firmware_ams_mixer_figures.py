#!/usr/bin/env python3
"""Plot verified smoothing, shaping, quantizing and gate mixer behavior."""
import csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_limiter_figures import axis,curve
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def staircase(c,points,color):
    for a,b in zip(points,points[1:]):c.line(a[0],a[1],b[0],a[1],color,2);c.line(b[0],a[1],b[0],b[1],color,2)

def main():
    d=json.loads((OUT/'ams-mixers-check.json').read_text());assert d['passed']
    c=Canvas(900,460);c.text(450,12,'Smoothing：上升和下降使用不同系数',24)
    c.text(450,53,'输入与输出均除以 4096；横轴为控制更新次数',13,GRAY)
    for col,(up,color) in enumerate([(80,BLUE),(20,TEAL)]):
        row=next(row for row in d['smoothing'] if row['up']==up);x=75+445*col
        c.text(x+150,92,f"上升 {up} / 下降 {row['down']}",16,color)
        xy=axis(c,x,145,300,200,[(0,'0'),(64,'64'),(128,'128'),(191,'191')],[(-1,'−1'),(0,'0'),(1,'1')],lambda v:v/191,lambda v:(v+1)/2)
        for a,b in zip(row['steps'],row['steps'][1:]):c.line(*xy(a['update'],a['input']/4096),*xy(b['update'],b['input']/4096),GRAY,1,True)
        curve(c,[xy(p['update'],p['output']/4096) for p in row['steps']],color)
    c.text(450,397,'灰虚线为输入；实线为原整数状态的输出。',13,GRAY)
    c.text(450,433,'平滑参数越大，表中系数越小；未据此推定实机秒数。',13,GRAY)
    c.save('ams-mixer-smoothing')

    c=Canvas(900,495);c.text(450,12,'Shape 与 Quantize：两种不同的幅度变换',23)
    c.text(450,53,'横纵轴均以 4096 为单位，输入范围为 −1 至 +1',13,GRAY)
    c.text(225,94,'Shape +99',17,BLUE);c.text(670,94,'Quantize',17,TEAL)
    maps=[]
    for x in [75,520]:
        maps.append(axis(c,x,160,300,205,[(-1,'−1'),(0,'0'),(1,'1')],[(-1,'−1'),(0,'0'),(1,'1')],lambda v:(v+1)/2,lambda v:(v+1)/2))
    for asymmetric,color in [(0,BLUE),(1,TEAL)]:
        rows=[p for p in d['shapes'] if p['asymmetric']==asymmetric and p['amount']==99]
        curve(c,[maps[0](p['input']/4096,p['output']/4096) for p in rows],color)
    for count,color in [(2,GOLD),(12,BLUE)]:
        rows=[p for p in d['quantized'] if p['count']==count and -4096<=p['input']<=4096]
        curve(c,[maps[1](p['input']/4096,p['output']/4096) for p in rows],color)
    for x,label,color in [(155,'Symmetric',BLUE),(307,'Asymmetric',TEAL),(610,'Steps 2',GOLD),(770,'Steps 12',BLUE)]:
        c.line(x-67,136,x-47,136,color,2);c.text(x,127,label,11,color)
    c.text(450,409,'Symmetric 保留零点；Asymmetric 可使零输入产生偏移。',13,GRAY)
    c.text(450,447,'Quantize 分别量化正负半轴，并将末档明确写为 ±4096。',13,GRAY)
    c.text(450,477,'曲线点和阶梯分界均由原指令核对。',12,GRAY)
    c.save('ams-mixer-shape-quantize')

    c=Canvas(900,570);c.text(450,12,'Gate：可在初始化时固定分支选择',24)
    c.text(450,53,'阈值为 0，初始判断为高；高低分支分别读取 B、A',13,GRAY)
    live=next(row for row in d['gates'] if (row['flags'],row['threshold'],row['control_source'],row['start_high'])==(6,0,11,1))
    held=next(row for row in d['gates'] if (row['flags'],row['threshold'],row['control_source'],row['start_high'])==(7,0,11,1))
    xy=axis(c,95,125,710,95,[(0,'0'),(3,'3'),(6,'6'),(9,'9'),(11,'11')],[(-1,'−1'),(0,'0'),(1,'+1')],lambda v:v/11,lambda v:(v+1)/2)
    staircase(c,[xy(p['update'],p['gate_input']) for p in live['steps']],GRAY);c.text(450,91,'门控来源（原整数值）',14,GRAY)
    xy=axis(c,95,310,710,145,[(0,'0'),(3,'3'),(6,'6'),(9,'9'),(11,'11')],[(-1,'−1'),(0,'0'),(1,'1')],lambda v:v/11,lambda v:(v+1)/2)
    for row,color in [(live,BLUE),(held,TEAL)]:staircase(c,[xy(p['update'],p['output']/4096) for p in row['steps']],color)
    for x,label,color in [(280,'持续比较门控来源',BLUE),(615,'固定初始化时的判断',TEAL)]:
        c.line(x-110,277,x-85,277,color,2);c.text(x,268,label,13,color)
    xx=95+710*6/11;c.line(xx,115,xx,455,GOLD,1,True);c.text(xx+102,237,'第 6 次重新初始化',12,GOLD)
    c.text(450,499,'固定的是分支选择；被选中的 A/B 来源仍继续更新。',14,BLUE)
    c.text(450,537,'等于阈值时选择高分支；曲线来自十二次受控调用。',13,GRAY)
    c.save('ams-mixer-gate')
    with (OUT/'ams-mixer-smoothing.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['rise_parameter','fall_parameter','update','input','output'])
        for row in d['smoothing']:
            for p in row['steps']:w.writerow([row['up'],row['down'],p['update'],p['input'],p['output']])
    with (OUT/'ams-mixer-transfer.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['mode','asymmetric','amount','steps','input','output'])
        for p in d['shapes']:w.writerow(['Shape',p['asymmetric'],p['amount'],'',p['input'],p['output']])
        for p in d['quantized']:w.writerow(['Quantize','','',p['count'],p['input'],p['output']])
    with (OUT/'ams-mixer-gate.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['flags','threshold','control_source','start_high','update','gate_input','reinitialize','latched','output'])
        for row in d['gates']:
            for p in row['steps']:w.writerow([row['flags'],row['threshold'],row['control_source'],row['start_high'],p['update'],p['gate_input'],p['reinitialize'],p['latched'],p['output']])
    print('Rendered three AMS mixer figures (PNG/SVG), with three source CSV files.')
if __name__=='__main__':main()
