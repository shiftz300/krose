#!/usr/bin/env python3
"""Working parameter data versus conditional song-buffer synchronization."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT

def main():
    r=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/parameter-notifications-check.json').read_text())
    assert r['passed']
    c=Canvas(900,480)
    c.text(450,15,'工作区更新之后，歌曲副本按状态同步',23)
    c.box(25,70,230,100,'当前工作区',['原参数回调写入字段','供当前运行状态读取'],BLUE)
    c.box(335,70,230,100,'变更通知',['操作码 8：新值 / 旧值','携带事件类型与临时标志'],TEAL)
    c.box(645,70,230,100,'效果参数快照',['效果选择值改变时','先复制 64 字节参数块'],GOLD)
    c.arrow(255,120,335,120);c.arrow(565,120,645,120)
    c.arrow(450,170,450,225)
    c.box(245,225,410,125,'检查歌曲同步资格',
          ['参数组 100–135，播放缓存没有该项记录','播放状态允许，临时标志为零','字段同步还会排除事件类型 18、20'],TEAL)
    c.arrow(450,350,450,390)
    c.box(245,390,410,70,'当前歌曲缓冲',['保存单项字段，或复制效果的 64 字节参数块'],BLUE)
    c.text(120,270,'门槛未满足',15,GRAY);c.text(120,296,'歌曲副本保持原值',13,GRAY)
    c.arrow(245,285,220,285,GRAY)
    c.save('parameter-song-sync')

if __name__=='__main__':main()
