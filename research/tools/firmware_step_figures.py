#!/usr/bin/env python3
"""Plot actual step-sequencer start/stop output."""
import json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY
from layout import PRODUCT_ROOT as ROOT
def main():
    d=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/step-sequencer-check.json').read_text());assert d['passed']
    c=Canvas(820,360);c.text(410,12,'步进序列器：中途停止与重新启动',23)
    c.text(410,50,'原指令逐 tick 执行；步长 120；Gate = 80%；Accent = +32',13,GRAY)
    left=100;scale=650/960;active={}
    for i,n in enumerate([36,38,42]):
        y=120+i*65;c.text(42,y-8,str(n),15,BLUE);c.line(left,y,750,y,GRAY)
    for e in d['transport']:
        if e['on']:active[e['note']]=e['tick']
        else:
            start=active.pop(e['note']);y=120+[36,38,42].index(e['note'])*65
            c.line(left+start*scale,y,left+e['tick']*scale,y,TEAL,5)
    for t,label in [(187,'停止 187'),(301,'重启 301')]:
        x=left+t*scale;c.line(x,90,x,275,GOLD,1,True);c.text(x,282,label,12,GOLD)
    c.text(410,327,'停止入口立即关闭尚未结束的音符；重启后从 Pattern 开头继续。',13,GRAY)
    c.save('step-start-stop')
    d=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/step-live-write-check.json').read_text())
    assert d['passed'] and len(d['song_cases'])==4096 and len(d['integrated'])==12
    c=Canvas(820,440);c.text(410,12,'步骤编辑：当前值、Pattern 与歌曲副本',23)
    c.text(410,49,'力度由 64 改为 99；原应用处理器与提交遍历连续执行',13,GRAY)
    c.box(20,90,230,110,'① 应用处理编辑记录',['当前编辑值：64 → 99','Pattern：仍为 64','生成新旧值记录'],BLUE)
    c.box(295,90,230,110,'② 通知提交回调',['操作码 8 解析当前步骤','Pattern 力度：64 → 99','Accent 使用同一提交链'],TEAL)
    c.box(570,90,230,110,'③ Sequencer 歌曲同步',['通过状态与缓存门槛','歌曲副本：64 → 99','否则保留原值'],GOLD)
    c.arrow(250,145,295,145);c.arrow(525,145,570,145)
    c.text(410,235,'歌曲同步的四项条件',17,BLUE)
    c.text(410,274,'参数组 100–135  ·  当前字段未被播放缓存标记',14,GRAY)
    c.text(410,305,'播放状态允许同步  ·  临时抑制标志为 0',14,GRAY)
    c.text(410,354,'3072 组 Pattern 写入 + 4096 组歌曲门槛 + 12 条应用连续提交',13,TEAL)
    c.text(410,395,'歌曲副本使用私有测试缓冲；文件保存和音符录制另行核对。',12,GRAY)
    c.save('step-edit-commit')
if __name__=='__main__':main()
