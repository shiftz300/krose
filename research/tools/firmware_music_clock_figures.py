#!/usr/bin/env python3
"""Plot original clock traces and the verified delay-control path."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT


def main():
    result = json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/music-clock-check.json').read_text())
    assert result['passed']
    c = Canvas(860, 450)
    c.text(430, 12, '内部音乐时钟：同样的访问次数，不同的节拍进度', 22)
    x, y, width, height = 82, 70, 690, 280
    for tick in [0, 1200, 2400, 3600, 4800]:
        yy = y+height-tick*height/4800
        c.line(x, yy, x+width, yy, '#e4edf3')
        c.text(x-34, yy-7, str(tick), 12, GRAY)
    for visit in [0, 500, 1000, 1500, 2000]:
        xx = x+visit*width/2000
        c.text(xx, y+height+12, str(visit), 12, GRAY)
    c.line(x, y, x, y+height)
    c.line(x, y+height, x+width, y+height)
    c.text(x+width/2, 384, '定时器访问次数', 14, GRAY)
    c.text(91, 45, '累计 tick', 13, GRAY)
    for tempo, color in [(4000, BLUE), (12000, TEAL), (30000, GOLD)]:
        trace = next(r for r in result['trajectories'] if r['tempo_raw'] == tempo)
        previous, total = (x, y+height), 0
        for visit, ticks in enumerate(trace['ticks_by_visit'], 1):
            total += ticks
            point = (x+visit*width/2000, y+height-total*height/4800)
            c.line(*previous, *point, color, 2)
            previous = point
        c.text(811, previous[1]-8, str(tempo//100), 14, color)
    c.text(430, 418, '标注为 BPM；轨迹来自原 ARM。480 tick 对应四分音符。', 13, GRAY)
    c.save('music-clock-counts')
    c = Canvas(900, 400)
    c.text(450, 12, '节拍计数怎样唤醒延迟声部', 24)
    cells = [(30, 70, '内部节拍发生器', ['64 位周期与余量', '变速在节拍边界生效']),
             (345, 70, '共享音乐计数', ['每个内部 tick 加一', '32 位计数允许回绕']),
             (660, 70, '音源管理器', ['读取本次 tick 差值', '通过原虚表调用 PCM 管理器']),
             (660, 240, '等待队列', ['先扣节拍，再扣固定等待', '全部到期：设置就绪 bit 3']),
             (345, 240, '后续控制访问', ['读取就绪标志', '更新音高并提交 TG 启动'])]
    for i, (xx, yy, title, lines) in enumerate(cells):
        c.box(xx, yy, 210, 105, title, lines, BLUE if i < 4 else GOLD)
    c.arrow(240, 122, 345, 122)
    c.arrow(555, 122, 660, 122)
    c.arrow(765, 175, 765, 240)
    c.arrow(660, 292, 555, 292, GOLD, True)
    c.text(145, 264, '原指令连通检查', 17, TEAL)
    c.text(145, 291, '4 段轨迹 × 2,000 次访问', 13, GRAY)
    c.text(450, 368, '实线：本次连通；虚线：阶段 03 已单独核对，尚未合并 OS 调度。', 13, GRAY)
    c.save('music-clock-delay')


if __name__ == '__main__':
    main()
