#!/usr/bin/env python3
"""Evidence-based arpeggio logic and event timing diagrams."""
import json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY,PALE
from layout import PRODUCT_ROOT as ROOT

def main():
    d=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/arpeggiator-check.json').read_text());assert d['passed']
    c=Canvas(820,490);c.text(410,12,'琶音：按键、Pattern 与输出事件',23)
    c.box(20,62,235,100,'按键集合',['键区 / 力度区 / 直通','Sort 决定排序，Latch 保留集合'])
    c.box(292,62,235,100,'Pattern 数据',['552 字节，64 个步骤','每步：音高 / Gate / 力度 / Flam'])
    c.box(565,62,235,100,'音乐 tick',['八种步长：40～480','Swing 改变选定步骤的时间'])
    c.arrow(137,162,137,208);c.arrow(409,162,409,208);c.arrow(682,162,682,208)
    c.box(20,208,780,87,'原指令生成步骤事件',['Tone → 按键或固定音高 → 移调 → 扫弦分时 → Note On / Note Off'],TEAL)
    c.arrow(410,295,410,320)
    c.box(20,320,780,75,'输出到分配层',['检查记录时间、音高、力度与开关；音源和 TG 音频尚未接入本组实验'],GOLD)
    c.text(410,420,'已核对 1280 个 Pattern 的 27486 个有效步骤',16,BLUE)
    c.text(410,453,'连续执行含 8 个原厂例子、4 类独立顺序检查和 36 组扫弦检查',13,GRAY)
    c.save('arpeggio-logic')
    c=Canvas(820,570);c.text(410,12,'Swing 与扫弦怎样改变时间',23)
    c.text(410,50,'步长 120 tick；Swing = +25；下图标出每一步的起点',14,GRAY)
    left=110;right=770;scale=(right-left)/960
    for row in d['timing']['examples']:
        y=110+row['grid']*66;c.text(45,y-9,['×1','×2','×4'][row['grid']],17,BLUE)
        c.line(left,y,right,y,GRAY)
        for step,tick in enumerate(row['times']):
            x=left+scale*tick;shifted=tick!=step*120
            c.line(x,y-7,x,y+7,GOLD if shifted else BLUE,2)
            c.text(x,y+11,str(tick),11,GOLD if shifted else GRAY)
    c.text(410,300,'正向扫弦：Flam = +50，Gate = 50%，按下 C4 / E4 / G4',15,TEAL)
    row=next(x for x in d['strums'] if x['flam']==50 and x['pitch']==0 and x['velocity']==80 and not x['fixed'])
    x0=165;scale=4.5
    for i,note in enumerate([60,64,67]):
        y=360+i*55;on=next(e['tick'] for e in row['events'] if e['on'] and e['note']==note)
        off=next(e['tick'] for e in row['events'] if not e['on'] and e['note']==note)
        c.text(75,y-9,['C4 (60)','E4 (64)','G4 (67)'][i],14)
        c.line(x0,y,x0+120*scale,y,PALE,2)
        c.line(x0+on*scale,y,x0+off*scale,y,TEAL,5)
        c.text(x0+on*scale,y+10,str(on),12,TEAL);c.text(x0+off*scale,y+10,str(off),12,TEAL)
    c.text(410,529,'实线为音符持续区间；数字取自原固件的连续输出轨迹，单位为 tick。',13,GRAY)
    c.save('arpeggio-timing')
    s=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/arpeggio-sync-check.json').read_text());assert s['passed']
    c=Canvas(820,470);c.text(410,12,'五种内置琶音的实际输出',23)
    c.text(410,49,'按下 C4 / E4 / G4；Sort 开启；Octave = 1；RANDOM 初始状态 = 1',13,GRAY)
    for kind,name in enumerate(['UP','DOWN','ALT1','ALT2','RANDOM']):
        row=next(x for x in s['presets'] if x['kind']==kind and x['octaves']==1 and x['sort']==1 and len(x['keys'])==3)
        y=110+kind*66;c.text(55,y-7,name,15,BLUE)
        notes=row['notes'][:12];points=[(140+54*j,y-(n-60)*3) for j,n in enumerate(notes)]
        for yy in [y,y-12,y-21]:c.line(125,yy,765,yy,PALE)
        for p,q in zip(points,points[1:]):c.line(*p,*q,TEAL,2)
        for (x,yy),n in zip(points,notes):
            c.draw.ellipse(((x-3)*2,(yy-3)*2,(x+3)*2,(yy+3)*2),fill=TEAL)
            c.svg.append(f'<circle cx="{x}" cy="{yy}" r="3" fill="{TEAL}"/>')
            c.text(x,y+14,{60:'C',64:'E',67:'G'}[n],12,GRAY)
    c.text(410,439,'ALT1 折返时省去重复端点；ALT2 在上下边界各重复一次。',14,GRAY)
    c.save('arpeggio-presets')
    c=Canvas(820,470);c.text(410,12,'第二个琶音怎样加入',23)
    c.text(410,49,'A 从 tick 0 播放；B 在 tick 121 触键；步长 120，拍长 480',14,GRAY)
    left=185;scale=565/840;trigger=left+121*scale
    c.line(trigger,90,trigger,292,GOLD,1,True);c.text(trigger+70,79,'B 触键',13,GOLD)
    base=next(x for x in s['dual'] if x['key_sync']==0 and x['trigger']==121)
    rows=[('A',base,0),('B · Sync 关闭',base,1),('B · Sync 开启',next(x for x in s['dual'] if x['key_sync']==1 and x['trigger']==121),1)]
    for j,(title,row,engine) in enumerate(rows):
        y=123+70*j;c.text(80,y-8,title,14,BLUE);c.line(left,y,750,y,GRAY)
        for e in row['events']:
            if e['on'] and e['engine']==engine and e['tick']<=840:
                x=left+e['tick']*scale;c.line(x,y-7,x,y+7,TEAL,2);c.text(x,y+12,str(e['tick']),11,GRAY)
    c.text(410,323,'Sync 关闭时的拍内选择',16,BLUE)
    c.box(55,356,320,65,'拍内位置 0–59',['直接追赶当前拍'],TEAL)
    c.box(435,356,320,65,'拍内位置 60–479',['等待下一拍'],GOLD)
    c.text(410,440,'数字对应输入先于 tick 的本组执行顺序；首步有时间差门槛。',12,GRAY)
    c.save('arpeggio-dual-sync')
if __name__=='__main__':main()
