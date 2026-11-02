#!/usr/bin/env python3
"""Verified channel-position cache and expressive-message coalescing."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT


def main():
    r = json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/sequence-controls-check.json').read_text())
    assert r['passed'] and len(r['cc_slot_map']) == 38
    c = Canvas(900, 485)
    c.text(450, 14, '控制事件按歌曲位置仲裁，压力与弯音可在队列中合并', 22)
    c.box(30, 70, 395, 142, '通道缓存：同一 CC 已应用到 tick 120',
          ['后来读到 tick 119 → 保留轨道记录，跳过该路输出',
           '后来读到 tick 120 → 允许再次输出',
           '本机、外发两套缓存分别判断'], BLUE)
    c.box(475, 70, 395, 142, '批处理：同轨连续压力值 1 → 2 → 3',
          ['本机队列最终只保留压力值 3',
           '外发路线仍按顺序输出 1、2、3',
           '条件：队列对象 +294 标志已启用'], TEAL)
    c.text(450, 246, '中间插入音符时：音符前后的压力各保留一个位置', 17)
    positions = [40, 255, 470, 685]
    for x, title, lines, color in zip(positions,
        ['压力 1 → 压力 2', 'Note On', '压力 3', '本机队列'],
        [['覆盖同一队列位置'], ['清除此轨合并标志'], ['申请新的队列位置'], ['压力 2 → 音符 → 压力 3']],
        [TEAL, BLUE, TEAL, GOLD]):
        c.box(x, 290, 175, 94, title, lines, color)
    for x in positions[:-1]: c.arrow(x+175, 337, x+215, 337)
    c.text(450, 426, '原事件解码、缓存比较和队列写入均执行；图中压力值来自合成事件的原 ARM 检查。', 13, GRAY)
    c.save('sequence-control-cache')


if __name__ == '__main__': main()
