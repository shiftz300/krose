#!/usr/bin/env python3
"""Song-position and verified tempo-event diagrams."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT


def main():
    r = json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/sequence-time-check.json').read_text())
    assert r['passed']
    c = Canvas(900, 380)
    c.text(450, 12, 'MIDI 定位按累计拍长计算，跨小节时读取新拍号', 22)
    x, y = 65, 80
    for units, title, label, color in [(16, '第 1 小节 · 4/4', '1920 tick', BLUE),
                                       (14, '第 2 小节 · 7/8', '1680 tick', TEAL),
                                       (44, '第 3 小节 · 11/4', '5280 tick', GOLD)]:
        c.box(x, y, units*10, 100, title, [label, str(units)+' 个定位单位'], color)
        x += units*10
    for pos in [0, 15, 16, 29, 30, 74]:
        xx = 65+pos*10
        c.line(xx, 183, xx, 201, GRAY)
        if pos not in [15, 29]: c.text(xx, 211, str(pos), 13, GRAY)
    c.text(450, 249, '位置 15 → 第 1 小节，tick 1800', 15, BLUE)
    c.text(450, 280, '位置 16 → 第 2 小节，tick 0', 15, TEAL)
    c.text(450, 311, '位置 30 → 第 3 小节，tick 0', 15, GOLD)
    c.text(450, 350, '一个定位单位 = 120 tick；小节编号在界面中从 1 开始。', 13, GRAY)
    c.save('song-position-meter')

    c = Canvas(900, 420)
    c.text(450, 12, '速度轨：事件到达指定位置后更新速度', 23)
    run = next(row for row in r['tempo_runs'] if row['mode'] == 0)['trace']
    x, y, w, h = 80, 85, 740, 235
    for bpm in [90, 120, 180, 240]:
        yy = y+h-(bpm-60)/210*h
        c.line(x, yy, x+w, yy, '#e4edf3')
        c.text(x-32, yy-8, str(bpm), 12, GRAY)
    c.text(93, 54, 'BPM', 13, GRAY)
    c.line(x, y, x, y+h)
    c.line(x, y+h, x+w, y+h)
    previous = None
    for p in run:
        tick = p['tick']+(1920 if p['bar_index'] else 0)
        point = (x+tick*w/3600, y+h-(p['effective_tempo']/100-60)/210*h)
        if previous:
            c.line(*previous, point[0], previous[1], TEAL, 2)
            c.line(point[0], previous[1], *point, TEAL, 2)
        previous = point
    for tick, label in [(0, '0'), (480, '480'), (1920, '1920'), (2220, '2220'), (3600, '3600')]:
        c.text(x+tick*w/3600, y+h+10, label, 12, GRAY)
    split = x+1920*w/3600
    c.line(split, y, split, y+h, GOLD, 1, True)
    c.text((x+split)/2, 57, '第 1 小节：4/4', 14, BLUE)
    c.text((split+x+w)/2, 57, '第 2 小节：7/8', 14, GOLD)
    c.text(450, 362, '横轴为从歌曲起点累计的 tick；第一小节长 1920，第二小节长 1680。', 13, GRAY)
    c.text(450, 392, '轨迹来自原事件遍历与速度设置函数；事件数据由夹具构造。', 13, GRAY)
    c.save('tempo-track-events')


if __name__ == '__main__': main()
