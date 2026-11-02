#!/usr/bin/env python3
"""Illustrate recovered Program routing and batched route changes."""
import json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT

def main():
    d=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/effect-routing-check.json').read_text());assert d['passed']
    p=d['factory'][0]
    assert p['program']=='A000' and p['source_bus']==1
    assert [(s['effect'],s['chain']) for s in p['ifx'][:2]]==[(7,True),(5,False)]
    assert p['ifx'][0]['targets'][1:4]==[0,0,0] and p['ifx'][1]['targets'][1:4]==[127,127,127]
    assert p['mfx_returns']==[0,30] and p['mfx_cross']==[0,0]
    c=Canvas(820,510);c.text(410,12,'A000 原厂钢琴：主音色的效果路径',23)
    c.box(25,80,150,90,'PCM 音源',['Program 总线 = IFX1'])
    c.box(230,80,190,90,'IFX1 · 四段 EQ',['串接到 IFX2','本槽 Send1/2 均为 0'])
    c.box(475,80,190,90,'IFX2 · 母带限制器',['串接关闭','Send1/2 均为 127'])
    c.arrow(175,125,230,125);c.arrow(420,125,475,125)
    c.box(475,240,190,90,'MFX2 · Hall',['原始发送 = 127','原始返回 = 30'],TEAL)
    c.arrow(570,170,570,240,TEAL)
    c.box(230,240,190,90,'MFX1 · No Effect',['原始发送 = 127','原始返回 = 0'],GRAY)
    c.line(510,170,510,205);c.line(325,205,510,205);c.arrow(325,205,325,240)
    c.box(705,155,95,90,'L/R',['直接输出','+ MFX 返回'],TEAL)
    c.line(665,125,752,125,TEAL);c.arrow(752,125,752,155,TEAL)
    c.line(665,285,752,285,TEAL);c.arrow(752,285,752,245,TEAL)
    c.box(25,350,290,85,'IFX5 · 立体声限制器',['槽位已启用；未连接到图中主音色链'],GRAY)
    c.text(550,365,'该图依据原配置与原路由刷新结果。',13,GRAY)
    c.text(550,389,'不包含鼓轨的独立输入和效果内部干湿。',13,GRAY)
    c.text(410,460,'返回量 30 是控制值；声音贡献还取决于算法、内部干湿和输入。',13,GOLD)
    c.save('effects-program-routing')
    c=Canvas(820,500);c.text(410,12,'路由切换会分批完成',23)
    cols=[(25,'原状态'),(300,'第一批'),(575,'第二批')]
    c.text(410,60,'IFX：从普通发送切换为串接',17,BLUE)
    for (x,title),lines in zip(cols,[['Send1 = 101','Send2 = 79'],['两路发送降到 0','直接输出关闭'],['更新串接目的地','开启串接传输']]):c.box(x,95,220,105,title,lines)
    c.arrow(245,147,300,147);c.arrow(520,147,575,147)
    c.text(410,238,'MFX：方向 B 切换为方向 A',17,TEAL)
    t=next(v for v in d['mfx_transitions'] if v['old_flags']==2 and v['new_flags']==3)
    assert [b['cached'] for b in t['batches']]==[[0,0],[127,0]]
    for (x,title),lines in zip(cols,[['A = 0','B = 127'],['A = 0','B = 0'],['A = 127','B = 0']]):c.box(x,275,220,105,title,lines,TEAL)
    c.arrow(245,327,300,327,TEAL);c.arrow(520,327,575,327,TEAL)
    c.text(410,421,'普通调用前 8 次延后，第 9 次提交；IFX 另有强制提交入口。',13,GRAY)
    c.text(410,449,'图示为原 ARM 控制写入顺序，音频渐变的实际时长尚未确定。',13,GOLD)
    c.save('effects-route-transitions')
    print('Rendered effects-program-routing and effects-route-transitions (PNG/SVG).')
if __name__=='__main__':main()
