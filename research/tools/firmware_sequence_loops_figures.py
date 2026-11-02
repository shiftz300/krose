#!/usr/bin/env python3
"""Loop source-bar mapping from original ARM results."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT


def main():
    r = json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/sequence-loops-check.json').read_text())
    assert r['passed']
    c = Canvas(900, 440)
    c.text(450, 14, '同一段循环，在歌曲时间线上重复读取源小节', 23)
    c.text(450, 54, '循环范围：M003–M004；图中小节编号从 1 开始', 15, GRAY)
    for row, intro in enumerate([1, 0]):
        y = 118+row*125
        c.text(89, y+20, '播放前奏：'+('开' if intro else '关'), 14, GRAY)
        bars = next(x['source_bars'] for x in r['mapping_examples'] if x['intro'] == intro)
        for i, source in enumerate(bars):
            x = 185+67*i
            color = GRAY if source < 2 else TEAL if source == 2 else BLUE
            c.box(x, y, 59, 74, f'M{source+1:03}', [], color)
            c.text(x+29, y+42, str(i+1), 12, GRAY)
    c.text(450, 365, '方框大字是读取的源小节；下方小字是当前歌曲小节。', 14, GRAY)
    c.text(450, 400, '原游标保留源数据，通过小节偏移和边界跳转生成连续播放位置。', 14, GRAY)
    c.save('sequence-loop-bars')


if __name__ == '__main__': main()
