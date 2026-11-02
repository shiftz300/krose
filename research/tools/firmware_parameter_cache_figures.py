#!/usr/bin/env python3
"""Recorded parameter cache and queue behavior from verified checks."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT

def main():
    r=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/parameter-cache-check.json').read_text())
    assert r['passed']
    c=Canvas(900,490)
    c.text(450,15,'歌曲参数：保存播放状态，再交给应用处理',23)
    c.box(25,65,225,105,'解码与本机路由',['SysEx → 命名空间 / 索引 / 值','通道与轨道门槛'],BLUE)
    c.box(335,65,230,105,'参数缓存',['保存值，更新两套标志','效果选择阻止旧参数重放'],TEAL)
    c.box(650,65,225,105,'应用队列',['按参数编号查找已有记录','决定覆盖或追加'],BLUE)
    c.arrow(250,117,335,117);c.arrow(565,117,650,117)
    c.arrow(450,170,450,210)
    c.box(315,210,270,105,'重放条件',['已有记录 = 1，禁止重放 = 0','满足时送回参数路由'],TEAL)
    c.line(315,262,137,262);c.arrow(137,262,137,170)
    c.text(450,350,'连续输入：11 → 22 → 33',18)
    c.box(55,390,350,77,'普通参数',['一条记录：33'],BLUE)
    c.box(495,390,350,77,'音色选择 / 效果相关参数',['三条记录：11、22、33'],GOLD)
    c.save('parameter-cache-queue')

if __name__=='__main__':main()
