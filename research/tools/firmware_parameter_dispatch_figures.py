#!/usr/bin/env python3
"""Queue rotation and live parameter storage, grounded in ARM checks."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT

def main():
    r=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/parameter-dispatch-check.json').read_text())
    assert r['passed'] and len(r['integrated'])==6
    c=Canvas(900,510)
    c.text(450,15,'先切换入队位置，再处理当前参数批次',23)
    c.box(30,70,230,100,'队列 A：当前批次',['保存待处理记录','本轮处理完后清空'],BLUE)
    c.box(640,70,230,100,'队列 B：接收新事件',['入队指针先切换到这里','下一轮与 A 互换'],TEAL)
    c.arrow(270,112,630,112);c.text(450,81,'切换入队指针',15)
    c.arrow(145,170,145,220)
    c.box(30,220,230,105,'逐项分派',['读取旧值，检查事件类型','效果参数先按描述符限幅'],BLUE)
    c.box(335,220,230,105,'原参数回调',['按字段宽度写入内存','再调用 getter 读取新值'],TEAL)
    c.box(640,220,230,105,'变更记录',['参数编号 / 类型 / 标志','新读回值 / 旧读回值'],GOLD)
    c.arrow(260,272,335,272);c.arrow(565,272,640,272)
    c.text(450,370,'已执行的例子：命名空间 100，索引 2，范围 0–7',18)
    c.box(75,413,210,70,'请求值 255',['缓存保留 32 位原值'],BLUE)
    c.box(345,413,210,70,'内存字节 255',['原单字节写入函数'],TEAL)
    c.box(615,413,210,70,'读回值 7',['getter 按描述符限幅'],GOLD)
    c.arrow(285,448,345,448);c.arrow(555,448,615,448)
    c.save('parameter-dispatch')

if __name__=='__main__':main()
