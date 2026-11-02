#!/usr/bin/env python3
"""PPAT layout and original packed replacement diagram."""
import json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY
from layout import PRODUCT_ROOT as ROOT
def main():
    d=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/drum-patterns-check.json').read_text());assert d['passed']
    c=Canvas(820,440);c.text(410,12,'PPAT 鼓轨库怎样装入与整理',23)
    cells=[(20,65,150,'文件头',['KSB0 / 64 字节']),
           (190,65,235,'目录',['999 项 × 32 字节','名称 / 原字段 / 事件指针']),
           (445,65,355,'事件池',['小节头 → 音符 → 下一小节 → 结束','133880 个八字节记录'])]
    for x,y,w,t,lines in cells:c.box(x,y,w,100,t,lines)
    c.arrow(170,115,190,115);c.arrow(425,115,445,115)
    c.text(410,191,'装载：按新基址修正全部非空指针，保持事件内容。',15,TEAL)
    c.box(20,240,235,95,'替换目标 Pattern',['计算新旧长度之差','允许替换为更长、较短或空内容'],TEAL)
    c.box(292,240,235,95,'搬移后续事件',['原 memmove 处理重叠','修正后续目录项的指针'],TEAL)
    c.box(565,240,235,95,'清理尾部',['更新目标目录项','清零已使用事件之后的空间'],TEAL)
    c.arrow(255,287,292,287);c.arrow(527,287,565,287)
    c.text(410,369,'已检查全部目录与 5517 个小节；24 次替换逐字节比较完整事件池。',13,GRAY)
    c.text(410,404,'图示为数据装载与编辑路径；鼓轨触发和实时播放继续追踪。',13,GOLD)
    c.save('drum-pattern-pool')
    p=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/drum-playback-check.json').read_text());assert p['passed']
    c=Canvas(820,360);c.text(410,12,'鼓轨循环、跨小节关音与停止',23)
    c.text(410,50,'合成单小节 Pattern；两圈逐 tick 执行；在 3839 停止',13,GRAY)
    left=100;scale=650/3840;active={}
    trace=next(x for x in p['synthetic'] if x['shift']==0)
    for j,n in enumerate([36,38,42]):
        y=120+j*60;c.text(45,y-8,str(n),15,BLUE);c.line(left,y,750,y,GRAY)
    for t,s,n,v in trace['events']:
        if s&240==144:active[n]=t
        else:
            begin=active.pop(n);y=120+[36,38,42].index(n)*60
            c.line(left+begin*scale,y,left+t*scale,y,TEAL,5)
    for t,label in [(0,'0'),(1920,'循环 1920'),(3839,'停止 3839')]:
        x=left+t*scale;c.line(x,90,x,263,GOLD,1,True);c.text(x,277,label,12,GOLD)
    c.text(410,323,'音符 42 的时长超出小节，在边界关音；第二圈首音在 1921 起音。',13,GRAY)
    c.save('drum-playback-loop')
    shared=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/music-interlock-check.json').read_text());assert shared['passed']
    row=next(x for x in shared['traces'] if x['stop_arp_at']==610)
    c=Canvas(820,330);c.text(410,12,'同一中央 tick 下的琶音与鼓轨',23)
    c.text(410,50,'琶音先运行；鼓轨在 121 触发并等待；610 关闭琶音',13,GRAY)
    left=100;scale=650/960
    for y,label in [(125,'琶音'),(215,'鼓轨')]:
        c.text(43,y-8,label,15,BLUE);c.line(left,y,750,y,GRAY)
    for e in row['arp']:
        if e['on']:
            x=left+e['tick']*scale;c.line(x,117,x,133,TEAL,3);c.text(x-12 if e['tick']==600 else x,140,str(e['tick']),11,GRAY)
    for t,s,n,v in row['drums']:
        if s&240==144:
            x=left+t*scale;c.line(x,207,x,223,TEAL,3);c.text(x-12 if t==600 else x,230,str(t),11,GRAY)
    x=left+610*scale;c.line(x,90,x,255,GOLD,1,True);c.text(x+60,88,'关闭琶音',12,GOLD)
    c.text(410,288,'610 之后琶音停止；鼓轨仍在 780 发出第三个音。',14,GRAY)
    c.save('music-interlock')
if __name__=='__main__':main()
