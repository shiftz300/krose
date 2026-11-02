#!/usr/bin/env python3
"""Draw original chorus control maps and recovered pre-EQ responses."""
import cmath,csv,json,math
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_limiter_figures import axis,curve
from firmware_chorus import centihz,delay_samples,depth_word,mix,Q23
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def response(coeff,hz):
    z=cmath.exp(-2j*math.pi*hz/48000);return (coeff[0]+coeff[1]*z)/(1-coeff[2]*z)
def main():
    d=json.loads((OUT/'chorus-check.json').read_text());assert d['passed']
    c=Canvas(840,440);c.text(420,12,'合唱：预延迟与自由 LFO 速率',23)
    c.text(235,60,'预延迟（ms）',16,BLUE)
    xy=axis(c,65,105,340,220,[(0,'0'),(50,'50'),(99,'99'),(135,'135')],[(0,'0'),(10,'10'),(30,'30'),(45,'45')],lambda x:x/135,lambda y:y/45)
    curve(c,[xy(i,delay_samples(i)/48) for i in range(136)],BLUE)
    c.text(235,365,'原始延迟值；写入地址偏移另加 1',13,GRAY)
    c.text(650,60,'LFO 显示频率（Hz）',16,TEAL)
    xy=axis(c,490,105,320,220,[(1,'1'),(99,'99'),(159,'159'),(230,'230')],[(0,'0'),(5,'5'),(10,'10'),(20,'20')],lambda x:(x-1)/229,lambda y:y/20)
    curve(c,[xy(i,centihz(i)/100) for i in range(1,231)],TEAL)
    c.text(650,365,'原始频率值；共四段步长',13,GRAY)
    c.text(420,410,'原参数换算已验证；DSP 的延迟插值和振荡器波形仍待恢复。',13,GOLD)
    c.save('chorus-delay-rate')
    c=Canvas(840,460);c.text(420,12,'Wet/Dry：湿声极性与中点电平',23)
    xy=axis(c,100,105,650,235,[(-100,'−100'),(-50,'−50'),(0,'0'),(50,'50'),(100,'100')],[(-1,'−1'),(0,'0'),(.75,'0.75'),(1,'1')],lambda x:(x+100)/200,lambda y:(y+1)/2)
    for j,color in [(0,BLUE),(1,TEAL)]:curve(c,[xy(i,mix(i)[j]/Q23) for i in range(-100,101)],color)
    c.line(268,76,292,76,BLUE,2);c.text(333,67,'湿声',13,BLUE)
    c.line(455,76,479,76,TEAL,2);c.text(520,67,'干声',13,TEAL)
    c.text(420,381,'原始 Wet/Dry；±50 时湿声绝对值和干声均约为 0.75',13,GRAY)
    c.text(420,421,'曲线显示原混合系数；MFX 的干声排除还需结合外层输出路径。',13,GOLD)
    c.save('chorus-signed-mix')
    c=Canvas(840,460);c.text(420,12,'前置高频 EQ：Mid-Hi 的系数上限',23)
    xy=axis(c,80,110,690,225,[(20,'20'),(100,'100'),(1000,'1k'),(10000,'10k'),(20000,'20k')],[(0,'0'),(5,'5'),(10,'10'),(15,'15')],lambda x:math.log(x/20)/math.log(1000),lambda y:y/15)
    rows=[]
    for fc,gain,color in [(1,24,BLUE),(1,30,GOLD),(0,30,TEAL)]:
        row=next(r for r in d['pre_eq'] if (r['band'],r['gain_raw'],r['fc'])==(1,gain,fc));points=[]
        for i in range(401):
            hz=20*1000**(i/400);db=20*math.log10(abs(response(row['coefficients'],hz)));points.append(xy(hz,db));rows.append([fc,gain,hz,db])
        curve(c,points,color)
    for x,color,label in [(170,BLUE,'Mid-Hi，+12 dB'),(430,GOLD,'Mid-Hi，+15 dB'),(680,TEAL,'High，+15 dB')]:
        c.line(x-78,81,x-57,81,color,2);c.text(x+12,72,label,12,color)
    c.text(420,376,'频率（Hz，对数坐标）；纵轴为原系数参考响应（dB）',13,GRAY)
    c.text(420,412,'Mid-Hi 的 +12.5 至 +15 dB 设置共用同一组系数；High 保持变化。',13,GOLD)
    c.save('chorus-pre-eq-cap')
    with (OUT/'chorus-control-maps.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['raw','delay_samples','frequency_centihz','depth_word'])
        for i in range(231):w.writerow([i,delay_samples(i) if i<=135 else '',centihz(i) if i else '',depth_word(i) if i<=100 else ''])
    with (OUT/'chorus-signed-mix.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['raw','wet_word','dry_word','wet_normalized','dry_normalized'])
        for i in range(-100,101):
            wet,dry=mix(i);w.writerow([i,wet,dry,wet/Q23,dry/Q23])
    with (OUT/'chorus-pre-eq-response.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['fc_raw','gain_raw','frequency_hz','reference_db']);w.writerows(rows)
    print('Rendered three chorus figures (PNG/SVG), with source CSV files.')
if __name__=='__main__':main()
