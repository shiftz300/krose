#!/usr/bin/env python3
"""Render verified voice LFO waveforms, random modes and fade-to-AMS flow."""
import csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_limiter_figures import axis,curve
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    d=json.loads((OUT/'voice-lfo-check.json').read_text());assert d['passed']
    c=Canvas(900,900);c.text(450,12,'音源 LFO：十二种周期波形',24)
    c.text(450,52,'Shape = 0，Offset = 0；横轴为一个周期，纵轴为输出 / 16384',13,GRAY)
    for i,row in enumerate(d['waveforms']):
        col,line=i%3,i//3;x,y=55+295*col,122+182*line
        c.text(x+110,y-35,str(i)+'  '+row['name'],14,BLUE)
        xy=axis(c,x,y,220,110,[(0,'0'),(.5,'0.5'),(1,'1')],[(-1,'−1'),(0,'0'),(1,'1')],lambda v:v,lambda v:(v+1)/2)
        curve(c,[xy(phase/65536,value/16384) for phase,value in row['points']],BLUE)
    c.text(450,862,'Guitar 的原表为单极性；波形不经过统一的正负归一化。',13,GRAY)
    c.save('voice-lfo-periodic')

    c=Canvas(900,670);c.text(450,12,'六种随机 LFO：保持与连续变化',24)
    c.text(450,52,'相同初始种子；原频率值 80；横轴为控制更新次数',13,GRAY)
    for i,kind in enumerate(range(12,18)):
        row=next(row for row in d['random_traces'] if row['wave']==kind and row['seed']==0x12345678)
        x,y=65+440*(i%2),125+166*(i//2);c.text(x+155,y-35,row['name'],16,BLUE if i<3 else TEAL)
        xy=axis(c,x,y,310,104,[(0,'0'),(128,'128'),(255,'255')],[(-1,'−1'),(0,'0'),(1,'1')],lambda v:v/255,lambda v:(v+1)/2)
        curve(c,[xy(row['tick'],row['value']/16384) for row in row['steps']],BLUE if i<3 else TEAL)
    c.text(450,627,'S/H 在换值前保持输出；cont 在相邻目标间插值。',13,GRAY)
    c.save('voice-lfo-random')

    c=Canvas(900,490);c.text(450,12,'LFO 淡入怎样进入调制系统',24)
    c.text(450,52,'Sine · Delay 1 · Fade 50 · 频率原值 80',14,GRAY)
    xy=axis(c,90,120,720,235,[(0,'0'),(40,'40'),(80,'80'),(120,'120'),(159,'159')],[(-1,'−1'),(0,'0'),(1,'1')],lambda v:v/159,lambda v:(v+1)/2)
    for key,scale,color in [('wave_output',16384,BLUE),('fade',65535,GOLD),('ams',4096,TEAL)]:
        curve(c,[xy(row['update'],row[key]/scale) for row in d['ams_source_trace']],color)
    for x,label,color in [(200,'原波形 / 16384',BLUE),(445,'淡入 / 65535',GOLD),(695,'AMS 输出 / 4096',TEAL)]:
        c.line(x-95,91,x-71,91,color,2);c.text(x,82,label,12,color)
    c.text(450,393,'控制更新次数；曲线使用各自标注的整数尺度',13,GRAY)
    c.text(450,430,'原波形先独立计算，再由 AMS 来源入口乘淡入系数。',14,BLUE)
    c.text(450,460,'显式推进控制状态，未测量宿主或实机的实际时间。',12,GRAY)
    c.save('voice-lfo-fade-ams')

    with (OUT/'voice-lfo-periodic.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['wave','name','phase_u16','output_s16'])
        for row in d['waveforms']:
            for phase,value in row['points']:w.writerow([row['wave'],row['name'],phase,value])
    with (OUT/'voice-lfo-random.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['wave','seed_initial','update','output_s16','phase_u16','rng_state'])
        for row in d['random_traces']:
            for step in row['steps']:w.writerow([row['wave'],row['seed'],step['tick'],step['value'],step['phase'],step['seed']])
    with (OUT/'voice-lfo-fade-ams.csv').open('w',newline='') as out:
        keys=['update','phase','wave_output','fade','ams','delay'];w=csv.DictWriter(out,keys);w.writeheader();w.writerows(d['ams_source_trace'])
    print('Rendered three voice LFO figures (PNG/SVG), with three source CSV files.')
if __name__=='__main__':main()
