#!/usr/bin/env python3
"""Evidence-based stage03 voice lifecycle figure; no simulated audio artwork."""
import json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY
from layout import PRODUCT_ROOT as ROOT

def main():
    d=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03/voice-tg-check.json').read_text())
    assert d['passed'] and d['automatic_reclaim']['final_available']==8
    c=Canvas(860,600);c.text(430,15,'声部从启动到回收',24)
    boxes=[(25,75,'建立控制状态',['音高 / 滤波 / 包络','LFO / AMS / 声像'],BLUE),
           (330,75,'写入 TG 参数',['采样模式与地址','控制目标与步长'],BLUE),
           (635,75,'提交启动位图',['普通：一个槽','立体声：两侧一起提交'],BLUE),
           (635,255,'演奏与保持',['控制周期更新目标','踏板可推迟释放'],TEAL),
           (330,255,'包络释放',['Note Off / 踏板松开','读回增益 → 释放目标'],TEAL),
           (25,255,'检测播放结束',['槽活动位清零','TG 全局状态 bit 3 清零'],TEAL),
           (25,445,'归还分配器',['可用计数增加','清理活动与延迟节点'],BLUE)]
    for x,y,title,lines,color in boxes:c.box(x,y,200,110,title,lines,color)
    c.arrow(225,130,330,130);c.arrow(530,130,635,130);c.arrow(735,185,735,255)
    c.arrow(635,310,530,310);c.arrow(330,310,225,310);c.arrow(125,365,125,445)
    c.text(278,104,'等待结束',12,GRAY);c.text(583,104,'就绪',12,GRAY)
    c.text(580,283,'允许释放',12,GRAY);c.text(275,283,'继续轮询',12,GRAY)
    c.box(330,445,505,110,'TG 内部音频仍待恢复',['上图已执行 ARM 控制代码，总线读写在模拟器边界截获。','采样推进、滤波传递函数与效果 DSP 尚未完成。'],GOLD)
    c.text(430,575,'正等待到期后启动；KeyOff 的负等待在松键时转为就绪。',13,GRAY)
    c.save('voice-lifecycle')
    r=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03/voice-reuse-check.json').read_text())
    assert r['passed']
    c=Canvas(860,400);c.text(430,12,'相同时间参数下，两种滑音方式的区别',23)
    for panel,title in enumerate(['Rate：音程越大，滑行越久','Time：不同音程同时到达']):
        x=70+panel*425;y=85;w=300;h=220;c.text(x+w/2,53,title,17)
        c.text(x-22,63,'音高',12,GRAY)
        for pitch in [60,72,84]:
            yy=y+h-(pitch-60)*h/24;c.line(x,yy,x+w,yy,'#edf3f6');c.text(x-22,yy-7,str(pitch),12,GRAY)
        c.line(x,y,x,y+h);c.line(x,y+h,x+w,y+h)
        for tick in [0,16,32,48,64]:c.text(x+tick*w/64,y+h+10,str(tick),12,GRAY)
        c.text(x+w/2,y+h+33,'控制访问次数',13,GRAY)
        for row in r['glide_series']:
            if row['scaled']!=bool(panel):continue
            points=[(x+pt['visit']*w/64,y+h-(pt['pitch_q16']/65536-60)*h/24) for pt in row['series']]
            color=BLUE if row['interval']==12 else TEAL
            for aa,bb in zip(points,points[1:]):c.line(*aa,*bb,color,2)
            c.line(points[-1][0],points[-1][1],x+w,points[-1][1],color,1,True)
    c.line(160,370,195,370,BLUE,2);c.text(257,360,'上行 12 半音',13,BLUE)
    c.line(370,370,405,370,TEAL,2);c.text(467,360,'上行 24 半音',13,TEAL)
    c.text(706,360,'原 ARM 轨迹；Time = 64',12,GRAY)
    c.save('portamento-modes')
if __name__=='__main__':main()
