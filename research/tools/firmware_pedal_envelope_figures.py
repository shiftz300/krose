#!/usr/bin/env python3
"""Plot verified CC64 time scales and auxiliary-envelope request cycles."""
import csv,json,math
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_limiter_figures import axis,curve
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def stairs(c,points,color):
    for a,b in zip(points,points[1:]):c.line(a[0],a[1],b[0],a[1],color,2);c.line(b[0],a[1],b[0],b[1],color,2)

def main():
    d=json.loads((OUT/'pedal-envelopes-check.json').read_text());assert d['passed']
    c=Canvas(900,480);c.text(450,12,'CC64：释放时间的动态缩放',24)
    c.text(450,53,'纵轴为原缩放值 / 256（对数坐标）；实际生效仍受调用门槛控制',13,GRAY)
    xy=axis(c,95,125,710,220,[(0,'0'),(32,'32'),(64,'64'),(96,'96'),(127,'127')],
            [(1,'1'),(10,'10'),(100,'100'),(1000,'1000')],lambda v:v/127,lambda v:math.log10(v)/3)
    for name,color,values in [('普通表，Sustain=0',BLUE,d['normal_scale_table']),
                              ('普通表，Sustain非零',TEAL,[d['normal_scale_table'][min(i,64)] for i in range(128)]),
                              ('运行态表 B',GOLD,d['special_scale_table'])]:
        curve(c,[xy(i,value/256) for i,value in enumerate(values)],color)
    for x,label,color in [(210,'普通表 / Sustain=0',BLUE),(480,'普通表 / Sustain非零',TEAL),(740,'运行态表 B',GOLD)]:
        c.line(x-100,96,x-75,96,color,2);c.text(x+7,87,label,11,color)
    c.text(450,387,'CC64 原值（0–127）',14,GRAY)
    c.text(450,428,'普通表且 Sustain 非零时，查表输入最高取 64，对应 819/256 倍。',13,BLUE)
    c.text(450,462,'两张原表及全部 CC64 输入均已执行原状态更新核对。',12,GRAY)
    c.save('pedal-release-scales')

    row=next(p for p in d['requests'] if (p['auxiliary_enabled'],p['initial_cc'],p['special'])==(1,0,0))
    c=Canvas(900,570);c.text(450,12,'踏板辅助包络：连续请求保留上次目标',23)
    c.text(450,52,'起音时 CC64=0；在第 0 / 64 / 128 / 192 次更新送入开启 / 关闭请求',13,GRAY)
    xy=axis(c,95,120,710,90,[(0,'0'),(64,'64'),(128,'128'),(192,'192'),(319,'319')],[(0,'0'),(127,'127')],lambda v:v/319,lambda v:v/127)
    stairs(c,[xy(p['update'],p['cc64']) for p in row['steps']],GRAY);c.text(450,88,'CC64（原值）',13,GRAY)
    xy=axis(c,95,310,710,150,[(0,'0'),(64,'64'),(128,'128'),(192,'192'),(319,'319')],[(0,'0'),(.25,'0.25'),(.5,'0.5')],lambda v:v/319,lambda v:v/.55)
    stairs(c,[xy(p['update'],p['aux_target']/32767) for p in row['steps']],GOLD)
    curve(c,[xy(p['update'],p['aux_level']/32767) for p in row['steps']],BLUE)
    for x,label,color in [(280,'当前辅助电平 / 32767',BLUE),(650,'保存目标 / 32767',GOLD)]:
        c.line(x-110,277,x-85,277,color,2);c.text(x,268,label,13,color)
    c.text(450,505,'两次开启后的目标为 16054、7865；关闭请求不会重置保存目标。',14,BLUE)
    c.text(450,546,'横轴为控制更新次数；辅助电平随后参与音量控制乘法。',12,GRAY)
    c.save('pedal-auxiliary-cycles')
    with (OUT/'pedal-release-scales.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['cc64','normal_sustain0','normal_sustain_nonzero','runtime_table_B'])
        for i in range(128):w.writerow([i,d['normal_scale_table'][i],d['normal_scale_table'][min(i,64)],d['special_scale_table'][i]])
    with (OUT/'pedal-auxiliary-cycles.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['auxiliary_enabled','initial_cc','special','update','cc64','aux_level','aux_stage','saved_target','amp_level','amp_control'])
        for row in d['requests']:
            for p in row['steps']:w.writerow([row['auxiliary_enabled'],row['initial_cc'],row['special'],p['update'],p['cc64'],p['aux_level'],p['aux_stage'],p['aux_target'],p['eg_levels'][2],p['amp']])
    with (OUT/'pedal-release-transitions.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['special','sustain','scaling_enabled','controller_enabled','update','cc64','scale','amp_level','amp_remaining','amp_stage'])
        for row in d['transitions']:
            for p in row['steps']:w.writerow([row['special'],row['sustain'],row['scaling'],row['enabled'],p['update'],p['cc64'],p['release_scale'],p['eg_levels'][2],p['eg_remaining'][2],p['eg_stages'][2]])
    print('Rendered two pedal-envelope figures (PNG/SVG), with three source CSV files.')
if __name__=='__main__':main()
