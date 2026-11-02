#!/usr/bin/env python3
"""Standalone SVG/PNG response plots using the repository's offline renderer."""
import csv,json,math
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY,PALE
from firmware_parametric_eq import response,decode
from layout import PRODUCT_ROOT as ROOT
BASE=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    d=json.loads((BASE/'parametric-eq-check.json').read_text());assert d['passed']
    def find(band,index,mode):return next(r for r in d['cases'] if (r['band'],r['index'],r['mode'],r['q'],r['gain'],r['delta'])==(band,index,mode,0,36,0))
    mid,low,high=find(1,500,0),find(0,49,1),find(3,0,1)
    frequencies=[20*1000**(i/400) for i in range(401)]
    curves=[]
    for hz in frequencies:
        curves.append([hz]+[20*math.log10(abs(response(c,hz))) for c in [mid['coefficients'][0],decode(mid['native'][0],1,1),low['coefficients'][0],high['coefficients'][0]]])
    with (BASE/'p4eq-response-curves.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['frequency_hz','band2_normalized_db','band2_unscaled_db','low_shelf_db','high_shelf_db']);w.writerows(curves)
    def plot(title,subtitle,series,name):
        c=Canvas(820,430);c.text(410,12,title,23);c.text(410,49,subtitle,13,GRAY)
        x0,y0,w,h=75,90,680,240
        def xy(hz,db):return x0+math.log10(hz/20)/3*w,y0+(24-db)/48*h
        for db in [-24,-18,-12,-6,0,6,12,18,24]:
            y=xy(20,db)[1];c.line(x0,y,x0+w,y,GRAY if db==0 else PALE);c.text(x0-28,y-7,str(db),11,GRAY)
        for hz in [20,50,100,200,500,1000,2000,5000,10000,20000]:
            x=xy(hz,0)[0];c.line(x,y0,x,y0+h,PALE);c.text(x,y0+h+9,str(hz//1000)+'k' if hz>=1000 else str(hz),11,GRAY)
        c.text(42,67,'dB',12,GRAY);c.text(410,360,'频率 / Hz（对数坐标）',12,GRAY)
        for i,(column,label,color,dash) in enumerate(series):
            for a,b in zip(curves,curves[1:]):c.line(*xy(a[0],a[column]),*xy(b[0],b[column]),color,2,dash)
            x=180+370*i;c.line(x-65,397,x-30,397,color,2,dash);c.text(x+75,388,label,12,color)
        c.save(name)
    plot('第二频段：系数缩放决定正确的增益','原参数：5050 Hz、Q = 0.5、+18 dB；该频段的缩放档位固定为 3',
         [(1,'还原缩放后的响应',TEAL,False),(2,'省略缩放的错误读取',GRAY,True)],'p4eq-coefficient-scale')
    plot('高、低搁架：从原系数得到的响应','两条曲线分别计算；低搁架 1000 Hz，高搁架 500 Hz，增益均为 +18 dB',
         [(3,'低搁架',BLUE,False),(4,'高搁架',GOLD,False)],'p4eq-shelves')
if __name__=='__main__':main()
