#!/usr/bin/env python3
"""Verified transport deferral and external-tempo filter figures."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT

BASE = ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    transport = json.loads((BASE/'transport-check.json').read_text())
    tempo = json.loads((BASE/'external-tempo-check.json').read_text())
    assert transport['passed'] and tempo['passed']
    c = Canvas(880, 430)
    c.text(440, 12, '定位尚未完成时，传输命令怎样继续', 23)
    cells = [(25, 75, 'Song Position 到达', ['请求计数加一', '记录定位标志']),
             (335, 75, 'Start / Continue 到达', ['写入待执行标志', '保留第一个命令']),
             (645, 75, '定位请求处理完成', ['请求计数减一', '计数清空后转交命令']),
             (645, 255, '生成待执行命令', ['Start → 3', 'Continue → 2']),
             (335, 255, '请求分发器', ['设置启动控制位', '恢复累计的时钟数']),
             (25, 255, '启动或继续操作', ['进入对应操作函数', '轨道定位与事件恢复待查'])]
    for i, (x, y, title, lines) in enumerate(cells):
        c.box(x, y, 210, 110, title, lines, GOLD if i == 5 else BLUE)
    c.arrow(235, 130, 335, 130)
    c.arrow(545, 130, 645, 130)
    c.arrow(750, 185, 750, 255)
    c.arrow(645, 310, 545, 310)
    c.arrow(335, 310, 235, 310, GOLD, True)
    c.text(440, 395, '原 ARM 连通到操作入口；虚线后的轨道主体在边界截获。', 13, GRAY)
    c.save('transport-deferred')

    c = Canvas(900, 440)
    c.text(450, 12, '外部速度读回：八项平均与延后刷新', 23)
    run = tempo['readback_runs'][0]['trace']
    x, y, w, h = 85, 85, 730, 255
    for bpm in [120, 160, 200, 240]:
        yy = y+h-(bpm-100)/160*h
        c.line(x, yy, x+w, yy, '#e4edf3')
        c.text(x-33, yy-8, str(bpm), 12, GRAY)
    c.text(96, 52, 'BPM', 13, GRAY)
    c.line(x, y, x, y+h)
    c.line(x, y+h, x+w, y+h)
    for n in [1, 30, 63, 100]: c.text(x+(n-1)*w/99, y+h+12, str(n), 12, GRAY)
    for field, color in [('raw_tempo', BLUE), ('readback', TEAL)]:
        previous = None
        for p in run:
            point = (x+(p['pulse']-1)*w/99, y+h-(p[field]/100-100)/160*h)
            if previous:
                c.line(*previous, point[0], previous[1], color, 2)
                c.line(point[0], previous[1], *point, color, 2)
            previous = point
    c.text(470, 140, '第 31 次输入变速', 14, BLUE)
    c.text(490, 285, '第 63 次才更新读回值', 14, TEAL)
    c.text(450, 385, '速度滤波器更新次数；输入从 120 BPM 变为 240 BPM', 14, GRAY)
    c.text(450, 414, '蓝色：估算速度输入　绿色：读回值。节拍周期在读回更新前已经改变。', 13, GRAY)
    c.save('external-tempo-readback')


if __name__ == '__main__': main()
