#!/usr/bin/env python3
"""Plot verified direct LFO depth conversion and separate fade/AMS paths."""
import csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_limiter_figures import axis,curve
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    d=json.loads((OUT/'lfo-targets-check.json').read_text());assert d['passed']
    c=Canvas(900,450);c.text(450,12,'Pitch LFO：原深度参数的分段换算',24)
    c.text(450,52,'正参数 0–99；纵轴为内部音高单位',14,GRAY)
    xy=axis(c,100,105,700,220,[(0,'0'),(25,'25'),(50,'50'),(60,'60'),(75,'75'),(99,'99')],
            [(0,'0'),(256,'256'),(1024,'1024'),(2048,'2048')],lambda v:v/99,lambda v:v/2300)
    curve(c,[xy(amount,value) for amount,value in d['depth_cases'] if amount>=0],BLUE)
    for amount,value,label in [(50,131,'50 → 131'),(60,256,'60 → 256'),(99,2254,'99 → 2254')]:
        x,y=xy(amount,value);c.line(x,y,x,325,TEAL,1,True)
        c.text(x-55 if amount==99 else x-25,y-25,label,12,TEAL)
    c.text(450,363,'原始深度参数',14,GRAY)
    c.text(450,405,'负参数取相反数；199 个合法值均执行原换算函数核对。',13,GRAY)
    c.save('lfo-target-pitch-depth')

    baseline=next(row['amp_before_eg'] for row in d['matrix'] if row['amount']==0 and row['routing']==0 and row['lfo']==[0,0])
    c=Canvas(960,490);c.text(480,12,'同一波形输出下，基础深度与力度 AMS 的淡入表现',22)
    c.text(480,52,'LFO1 输出固定 16384，LFO2 为零；力度 100；两种深度分别设 +99',13,GRAY)
    for x,label,color in [(285,'基础深度',BLUE),(640,'仅力度 AMS 深度',TEAL)]:
        c.line(x-88,91,x-63,91,color,2);c.text(x,82,label,13,color)
    specs=[('音高偏移（内部单位）',[(0,'0'),(1024,'1024'),(2254,'2254')],lambda row:row['pitch_word']-17664,2300),
           ('Filter A 截止控制字',[(0,'0'),(16000,'16000'),(31744,'31744')],lambda row:row['filters'][0][1],32768),
           ('包络前音量控制 / 基线',[(0,'0'),(1,'1'),(2,'2')],lambda row:row['amp_before_eg']/baseline,2.2)]
    for col,(title,ticks,get,maximum) in enumerate(specs):
        x=70+320*col;c.text(x+110,119,title,14,BLUE)
        xy=axis(c,x,170,220,190,[(0,'0'),(50,'50'),(100,'100')],ticks,lambda v:v/100,lambda v:v/maximum)
        for mode,color in [('base',BLUE),('velocity_ams',TEAL)]:
            rows=[row for row in d['fade_sweep'] if row['mode']==mode];curve(c,[xy(row['fade_index'],get(row)) for row in rows],color)
    c.text(480,405,'淡入量（%）；每个曲线点均由原三个目标函数执行核对',13,GRAY)
    c.text(480,442,'力度 AMS 深度在淡入为零时仍可生效；Filter 图中保留截止上限。',14,BLUE)
    c.text(480,473,'图示为控制结果；截止字未换算为 Hz，音量控制未换算为音频 dB。',12,GRAY)
    c.save('lfo-target-fade-paths')
    with (OUT/'lfo-target-pitch-depth.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['raw_depth','pitch_units']);w.writerows(d['depth_cases'])
    with (OUT/'lfo-target-fade-paths.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['mode','fade_percent','fade_u16','pitch_word','increment','filterA_cutoff','amplitude_before_eg','amplitude_after_eg'])
        for row in d['fade_sweep']:w.writerow([row['mode'],row['fade_index'],row['fades'][0],row['pitch_word'],row['increment'],row['filters'][0][1],row['amp_before_eg'],row['amp']])
    print('Rendered two LFO target figures (PNG/SVG), with two source CSV files.')
if __name__=='__main__':main()
