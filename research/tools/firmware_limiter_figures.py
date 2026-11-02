#!/usr/bin/env python3
"""Plot verified limiter control maps and native sidechain-EQ responses."""
import csv,json,math
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD,PALE
from firmware_limiters import ratio,attack_word,release_word,release_ms,Q23
from firmware_parametric_eq import response
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def axis(c,x,y,w,h,xticks,yticks,xmap,ymap):
    for value,label in yticks:
        yy=y+h-h*ymap(value);c.line(x,yy,x+w,yy,PALE);c.text(x-26,yy-8,label,11,GRAY)
    for value,label in xticks:
        xx=x+w*xmap(value);c.line(xx,y+h,xx,y+h+4,GRAY);c.text(xx,y+h+10,label,11,GRAY)
    c.line(x,y,x,y+h);c.line(x,y+h,x+w,y+h)
    return lambda a,b:(x+w*xmap(a),y+h-h*ymap(b))
def curve(c,points,color):
    for a,b in zip(points,points[1:]):c.line(*a,*b,color,2)

def main():
    d=json.loads((OUT/'limiters-check.json').read_text());assert d['passed']
    c=Canvas(840,460);c.text(420,12,'立体声限制器：原始参数的换算',23)
    c.text(233,52,'压缩比 R:1',16,BLUE)
    xy=axis(c,65,105,340,240,[(0,'0'),(45,'45'),(90,'90'),(130,'130')],[(1,'1'),(10,'10'),(30,'30'),(50,'50')],lambda x:x/130,lambda y:(y-1)/49)
    curve(c,[xy(i,ratio(i)) for i in range(131)],BLUE)
    c.text(230,385,'原始 Ratio；131 为 Inf:1',13,GRAY)
    c.text(647,52,'Attack / Release 原生系数',16,TEAL)
    xy=axis(c,490,105,320,240,[(1,'1'),(25,'25'),(50,'50'),(75,'75'),(100,'100')],[(1,'1'),(.1,'0.1'),(.01,'0.01'),(.001,'0.001'),(.0001,'1e-4')],lambda x:(x-1)/99,lambda y:(math.log10(y)+5)/5)
    curve(c,[xy(i,attack_word(i)/Q23) for i in range(1,101)],BLUE)
    curve(c,[xy(i,release_word(i)/Q23) for i in range(1,101)],TEAL)
    c.line(545,87,567,87,BLUE,2);c.text(601,78,'Attack',11,BLUE)
    c.line(667,87,689,87,TEAL,2);c.text(728,78,'Release',11,TEAL)
    c.text(650,385,'原始时间参数 1–100',13,GRAY)
    c.text(420,424,'曲线表示控制系数；对应的音频时常数尚未确定。',13,GOLD)
    c.save('limiter-control-maps')
    c=Canvas(840,430);c.text(420,12,'母带限制器：释放时间与原生系数',23)
    xy=axis(c,100,90,650,230,[(.5,'0.5'),(1,'1'),(10,'10'),(100,'100'),(1000,'1000')],[(0,'0'),(.25,'0.25'),(.5,'0.50'),(.75,'0.75'),(1,'1.00')],lambda x:math.log(x/.5)/math.log(2000),lambda y:y)
    curve(c,[xy(release_ms(i),d['master_release_table'][i-10]/Q23) for i in range(10,291)],TEAL)
    c.text(420,358,'显示时间 t（ms，对数坐标）',13,GRAY)
    c.text(420,391,'t > 0.5：c ≈ 10^[−1 / (48 × (t − 0.5))]；t = 0.5：c = 0',14,BLUE)
    c.save('mastering-release-map')
    c=Canvas(840,430);c.text(420,12,'侧链 EQ：由原系数计算的频率响应',23)
    xy=axis(c,80,95,690,230,[(20,'20'),(100,'100'),(1000,'1k'),(10000,'10k'),(20000,'20k')],[(-18,'−18'),(-9,'−9'),(0,'0'),(9,'9'),(18,'18')],lambda x:math.log(x/20)/math.log(1000),lambda y:(y+18)/36)
    rows=[]
    for gain,color in [(-36,TEAL),(12,BLUE),(36,GOLD)]:
        row=next(v for v in d['side'] if (v['frequency_raw'],v['q_raw'],v['gain_raw'])==(50,12,gain));points=[]
        for i in range(401):
            hz=20*1000**(i/400);db=20*math.log10(abs(response(row['coefficients'],hz)));points.append(xy(hz,db));rows.append([gain,hz,db])
        curve(c,points,color)
    c.text(420,59,'中心频率 1000 Hz · Q = 1.7 · 增益 −18 / +6 / +18 dB',14,GRAY)
    c.text(420,363,'频率（Hz，对数坐标）；纵轴为参考传递函数增益（dB）',13,GRAY)
    c.text(420,394,'侧链 EQ 的系数已恢复；完整限制器的音频处理仍待确认。',13,GOLD)
    c.save('limiter-sidechain-eq')
    with (OUT/'limiter-control-maps.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['raw','ratio','ratio_is_infinite','attack_word','release_word'])
        for i in range(132):w.writerow([i,ratio(i),i==131,attack_word(i) if 1<=i<=100 else '',release_word(i) if 1<=i<=100 else ''])
    with (OUT/'mastering-release-map.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['raw','milliseconds','word','normalized_word'])
        for i in range(10,291):w.writerow([i,release_ms(i),d['master_release_table'][i-10],d['master_release_table'][i-10]/Q23])
    with (OUT/'limiter-sidechain-response.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['gain_raw','frequency_hz','reference_db']);w.writerows(rows)
    print('Rendered three limiter figures (PNG/SVG), with three source CSV files.')
if __name__=='__main__':main()
