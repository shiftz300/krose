#!/usr/bin/env python3
"""Recorded SysEx blocks and verified playback split."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT


def main():
    r=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/sequence-sysex-check.json').read_text())
    assert r['passed']
    c=Canvas(900,470)
    c.text(450,14,'SysEx 由一个事件头、若干数据块和结束块组成',23)
    for x,w,title,lines in [(25,170,'0F · 事件头',['时间位置 / 标志']),
                          (220,210,'07 · 数据块',['每块 7 个数据字节','按 +7 → +1 顺序读取']),
                          (455,210,'07 · 后续数据块',['FF 为填充，跳过','继续读取到结束块']),
                          (690,185,'08 · 结束块',['结束本条记录'])]:
        c.box(x,65,w,104,title,lines)
    for start,end in [(195,220),(430,455),(665,690)]:c.arrow(start,117,end,117)
    c.arrow(450,175,450,215)
    c.text(450,220,'检查消息头与固定块结构',17)
    c.arrow(410,250,220,290);c.arrow(490,250,680,290)
    c.box(35,290,370,105,'普通 SysEx',
          ['补上 F0 / F7，去掉 FF 填充','按轨道开关送往本机字节解析器和两个端口'],TEAL)
    c.box(495,290,370,105,'KORG 参数消息',
          ['42 3n 00 01 49 41 04 …','解出通道、参数组、索引与 32 位值'],GOLD)
    c.text(450,430,'检查执行原记录读取、分类与路由；本机解析、参数写入及端口缓冲在边界截获。',13,GRAY)
    c.save('sequence-sysex-blocks')


if __name__=='__main__':main()
