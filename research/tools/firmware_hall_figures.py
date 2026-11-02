#!/usr/bin/env python3
"""Plot verified Hall address intervals and native control coefficients."""
import csv,json,math
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD,PALE
from firmware_limiter_figures import axis,curve
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
COLORS=[BLUE,TEAL,GOLD,'#855685']
def main():
    d=json.loads((OUT/'hall-check.json').read_text());assert d['passed'];initial=d['initial_constants']
    c=Canvas(840,480);c.text(420,12,'Hall：与衰减表对应的四段延迟地址',23)
    c.text(420,57,'地址以本槽位的存储起点为零',13,GRAY)
    def x(value):return 110+value/27000*590
    for value in [0,5000,10000,15000,20000,25000]:
        xx=x(value);c.line(xx,95,xx,369,PALE);c.text(xx,382,str(value),11,GRAY)
    for i,(row,color) in enumerate(zip(d['delay_intervals'],COLORS)):
        y=105+65*i;start,end=initial[row['start_index']],initial[row['end_index']];assert end-start==row['length']
        c.text(53,y+4,'回路 '+str(i+1),14,color);c.line(x(start),y+12,x(end),y+12,color,7)
        c.line(x(start),y+4,x(start),y+22,color,2);c.line(x(end),y+4,x(end),y+22,color,2)
        c.text((x(start)+x(end))/2,y+26,str(row['length'])+' samples',12,color)
        c.text(759,y+4,f"{row['length']/48:.2f} ms",13,color)
    c.text(420,422,'长度由原地址差计算，且同时解释全部四组时间系数。',13,GRAY)
    c.text(420,450,'图示表示地址区间；扩散结构和回路间连接仍待恢复。',13,GOLD)
    c.save('hall-delay-intervals')
    c=Canvas(840,475);c.text(420,12,'Hall：时间与阻尼控制',23)
    c.text(235,62,'每回路衰减表幅度（dB）',16,BLUE)
    xy=axis(c,65,115,340,230,[(.1,'0.1'),(1,'1'),(10,'10')],[(-72,'−72'),(-48,'−48'),(-24,'−24'),(0,'0')],lambda x:math.log10(x/.1)/2,lambda y:(y+72)/72)
    for line,color in enumerate(COLORS):
        rows=[v for v in d['decays'] if v['line']==line];curve(c,[xy(v['seconds'],20*math.log10(abs(v['signed_gain']))) for v in rows],color)
    c.text(235,388,'设定时间 T（s，对数坐标）',13,GRAY)
    c.text(650,62,'阻尼控制值 / 8388607',16,TEAL)
    xy=axis(c,490,115,320,230,[(0,'0'),(50,'50'),(100,'100')],[(0,'0'),(.5,'0.5'),(1,'1')],lambda x:x/100,lambda y:y)
    for line,color in enumerate(COLORS):
        curve(c,[xy(raw,(raw*8388607//100)*d['damp_weights'][line]//d['damp_weights'][0]/8388607) for raw in range(101)],color)
    c.text(650,388,'原始 HiDamp（%）',13,GRAY)
    for line,color in enumerate(COLORS):
        x0=105+180*line;c.line(x0-18,93,x0,93,color,2);c.text(x0+38,84,'回路 '+str(line+1),11,color)
    c.text(420,436,'曲线来自原表和控制字；完整 Hall 音频网络尚未执行。',13,GOLD)
    c.save('hall-decay-damping')
    with (OUT/'hall-decay-tables.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['time_raw','seconds','line','length_samples','table_value','signed_gain','isolated_loop_t60','relative_t60_error'])
        for row in d['decays']:w.writerow([row[k] for k in ['time_raw','seconds','line','length','table_value','signed_gain','isolated_loop_t60','relative_t60_quantization_error']])
    with (OUT/'hall-damping-map.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['raw','line','weight','word'])
        for raw in range(101):
            for line,weight in enumerate(d['damp_weights']):w.writerow([raw,line,weight,(raw*8388607//100)*weight//d['damp_weights'][0]])
    with (OUT/'hall-isolated-loop-impulses.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['time_raw','line','frame','amplitude'])
        for row in d['isolated_loop_impulses']:
            for frame,value in row['events']:w.writerow([row['time_raw'],row['line'],frame,value])
    print('Rendered two Hall figures (PNG/SVG), with three source CSV files.')
if __name__=='__main__':main()
