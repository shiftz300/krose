#!/usr/bin/env python3
"""Render the original record intake and bounded FIFO data flow."""
import json,struct
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY
from layout import PRODUCT_ROOT as ROOT
def main():
    d=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/record-intake-check.json').read_text())
    assert d['passed'] and len(d['drum_trace'])==4
    c=Canvas(820,470);c.text(410,12,'鼓轨音符怎样进入录制缓冲',23)
    c.box(20,70,225,100,'鼓轨输出',['模式 3 + 活动标志','播放消息交接','原录制入口 243ED4'],BLUE)
    c.box(295,70,230,100,'录制筛选',['录制开关 / 通道映射','状态字节低四位重写','加入小节与 tick'],TEAL)
    c.box(575,70,225,100,'12 字节临时记录',['普通事件容量 120','控制入口容量 128','128 槽循环读写'],BLUE)
    c.arrow(245,120,295,120);c.arrow(525,120,575,120)
    c.box(295,230,230,110,'消费者缓存',['出队 → 当前记录副本','重复读取保留当前记录','确认后继续下一项'],TEAL)
    c.line(687,170,687,285);c.arrow(687,285,525,285)
    c.box(20,230,225,110,'歌曲事件生成',['音符配对 / 时长 / 量化','八字节歌曲事件','已验证单小节写入'],TEAL)
    c.arrow(295,285,245,285)
    events=' → '.join(str(e['tick']) for e in d['drum_trace'])
    c.text(410,378,'已接通的连续鼓轨记录：tick '+events,15,TEAL)
    c.text(410,421,'已接通歌曲写入与跨小节读回；机内录制研究在此归档。',12,GRAY)
    c.save('record-intake')
    d=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/record-notes-check.json').read_text())
    assert d['passed'] and len(d['cases'])==4560
    notes=[struct.unpack_from('<BBBBHH',bytes.fromhex(d['duplicate_notes_hex']),i*8) for i in range(2)]
    c=Canvas(820,400);c.text(410,12,'重复同音：量化起点，按顺序配对关音',23)
    c.text(410,49,'间隔 30；音高 60；两次按键重叠；原消费者直接写入歌曲缓冲',13,GRAY)
    left,scale=180,4.5
    for t in range(0,121,30):
        x=left+t*scale;c.line(x,95,x,300,GRAY,1,True);c.text(x,307,str(t),12,GRAY)
    for i,((start,end),note) in enumerate(zip([(3,63),(31,90)],notes)):
        y=122+i*105;c.text(76,y-9,'同音键 '+str(i+1),15,BLUE)
        c.line(left+start*scale,y,left+end*scale,y,GOLD,4)
        c.text(left+start*scale,y-25,str(start),11,GOLD);c.text(left+end*scale,y-25,str(end),11,GOLD)
        tick,duration=note[5],note[4]
        c.line(left+tick*scale,y+40,left+(tick+duration)*scale,y+40,TEAL,5)
        c.text(75,y+31,'歌曲记录',12,TEAL)
        c.text(left+(tick+duration/2)*scale,y+51,'起点 '+str(tick)+' / 时长 '+str(duration),12,TEAL)
    c.text(410,357,'金色：原始按键时间；绿色：歌曲中的量化起点与回填时长。',13,GRAY)
    c.save('record-note-pair')
    d=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/record-bars-check.json').read_text())
    assert d['passed'] and len(d['cases'])==1710 and len(d['replays'])==144
    row=next(r for r in d['cases'] if r['meters'][0]==19 and r['grid']==1 and r['start']==1799 and r['endbar']==3 and r['endtick']==119)
    c=Canvas(820,400);c.text(410,12,'跨拍号持续音：四条记录，一次起音',23)
    c.text(410,49,'原录制结果直接交给原播放器；音高与力度贯穿所有续接记录',13,GRAY)
    for i,code in enumerate(row['meters'][:4]):
        numerator=(code&15)+1;denominator=1<<((code>>4)+1);x=20+200*i
        position=str(row['quantized']) if i==0 else '7FFF'
        duration=str(row['endtick']) if i==3 else '7FFF'
        c.box(x,90,180,125,'小节 '+str(i)+' · '+str(numerator)+'/'+str(denominator),
              ['起点字段 '+position,'时长字段 '+duration,'小节记录数 2'],TEAL)
        if i<3:c.arrow(x+180,150,x+200,150)
    c.text(410,250,'播放读回',17,BLUE)
    c.text(410,287,'起音 (0, 1799)  →  中间小节持续保持  →  关音 (3, 119)',15,TEAL)
    c.text(410,345,'7FFF 表示持续或续接；每小节的两项记录为小节头和音符。',13,GRAY)
    c.save('record-held-bars')
if __name__=='__main__':main()
