#!/usr/bin/env python3
"""Plot verified LFO frequency AMS factors and native update dependencies."""
import csv,json,math
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_limiter_figures import axis,curve
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    d=json.loads((OUT/'voice-lfo-integration-check.json').read_text());assert d['passed']
    c=Canvas(900,500);c.text(450,12,'频率 AMS：原查表产生的更新尺度',24)
    c.text(450,53,'纵轴为 F / 256（对数坐标）；Amount AMS 关闭',14,GRAY)
    xy=axis(c,100,120,700,245,[(-1,'−1'),(-.5,'−0.5'),(0,'0'),(.5,'0.5'),(1,'1')],
            [(1/64,'1/64'),(1/8,'1/8'),(1,'1'),(8,'8'),(64,'64')],lambda v:(v+1)/2,lambda v:(math.log2(v)+7)/14)
    for amount,color in [(-99,TEAL),(50,GOLD),(99,BLUE)]:
        rows=[row for row in d['factor_sweeps'] if row['amount']==amount]
        curve(c,[xy(row['source']/4096,row['factor']/256) for row in rows],color)
    for x,amount,color in [(210,-99,TEAL),(450,50,GOLD),(690,99,BLUE)]:
        c.line(x-75,94,x-50,94,color,2);c.text(x+13,85,'Amount '+str(amount),12,color)
    c.text(450,404,'AMS 来源值 / 4096',14,GRAY)
    c.text(450,445,'来源 +4096、Amount +99：F = 16925，即 66.113 倍。',14,BLUE)
    c.text(450,475,'数值来自原指令检查；实际相位仍受频率表、同步和上限约束。',12,GRAY)
    c.save('voice-lfo-rate-factors')

    c=Canvas(900,700);c.text(450,12,'两组频率调制共同推进 LFO 状态',24)
    c.box(30,85,350,95,'第一组频率 AMS',['Amount + (Amount AMS × 来源 >> 12)','再乘 AMS1 来源'],BLUE)
    c.box(520,85,350,95,'第二组频率 AMS',['Amount2 × AMS2 来源'],TEAL)
    c.box(80,230,250,95,'整数调制与原表',['限幅 → 查表','输出 F1；默认 256'],BLUE)
    c.box(570,230,250,95,'整数调制与原表',['限幅 → 查表','输出 F2；默认 256'],TEAL)
    c.arrow(205,180,205,230,BLUE);c.arrow(695,180,695,230,TEAL)
    c.box(250,385,400,95,'合并更新尺度',['scale = min((F1 × F2) >> 8, 2147483647)'],BLUE)
    c.line(205,325,205,360,BLUE);c.line(205,360,365,360,BLUE);c.arrow(365,360,365,385,BLUE)
    c.line(695,325,695,360,TEAL);c.line(695,360,535,360,TEAL);c.arrow(535,360,535,385,TEAL)
    c.box(30,535,350,85,'Delay / Fade',['同一 scale 改变等待与淡入速度'],GOLD)
    c.box(520,535,350,85,'相位推进',['自由频率或音乐时钟；可单独暂停'],TEAL)
    c.line(350,480,350,505,GOLD);c.line(350,505,205,505,GOLD);c.arrow(205,505,205,535,GOLD)
    c.line(550,480,550,505,TEAL);c.line(550,505,695,505,TEAL);c.arrow(695,505,695,535,TEAL)
    c.text(450,650,'状态推进和波形求值都按 LFO2 → LFO1；交叉调制保留此顺序。',14,BLUE)
    c.text(450,678,'图示为原声部 LFO 子链；完整声部调度与音频输出另行连接。',12,GRAY)
    c.save('voice-lfo-rate-path')
    with (OUT/'voice-lfo-rate-factors.csv').open('w',newline='') as out:
        w=csv.DictWriter(out,['amount','source','factor']);w.writeheader();w.writerows(d['factor_sweeps'])
    with (OUT/'voice-lfo-feedback.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['update','scale_lfo1','scale_lfo2','output_lfo1','output_lfo2','phase_lfo1','phase_lfo2'])
        for row in d['feedback']:w.writerow([row['update'],*row['scales'],*row['outputs'],*row['phases']])
    print('Rendered two voice LFO frequency figures (PNG/SVG), with two source CSV files.')
if __name__=='__main__':main()
