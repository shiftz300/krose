#!/usr/bin/env python3
"""Plot verified mono fallback events and exact Unison distribution tables."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GRAY, GOLD
from layout import PRODUCT_ROOT as ROOT

DATA = ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'


def main():
    mono = json.loads((DATA/'mono-keys-check.json').read_text())
    unison = json.loads((DATA/'unison-check.json').read_text())
    assert mono['passed'] and unison['passed']
    c = Canvas(900, 460)
    c.text(450, 12, '同一段按键，三种单音优先级', 24)
    columns = ['按下 60', '按下 64', '按下 62', '松开 62', '松开 64', '松开 60']
    for i, title in enumerate(columns):
        x = 170+130*i
        c.text(x, 60, title, 15)
        c.text(x, 83, ['力度 40', '力度 80', '力度 100', '', '', ''][i], 12, GRAY)
    rows = [r for r in mono['timbre_timelines'] if r['scenario'] == 0 and not r['legato']]
    for row_index, row in enumerate(rows):
        y = 120+100*row_index
        c.text(55, y+20, row['priority'], 18, BLUE)
        for i, event in enumerate(row['rows']):
            x = 120+130*i
            starts = [e for e in event['dispatch'] if e[0] == 'on']
            title = str(event['keys'][0]) if event['keys'] else '释放'
            text = '触发力度 '+str(starts[0][3]) if starts else ('保持当前音' if event['keys'] else '无按住音符')
            c.box(x, y, 100, 80, title, [text], TEAL if starts else GRAY)
            if i < 5:
                c.arrow(x+100, y+40, x+130, y+40)
    c.text(450, 430, '原 ARM 调用轨迹；Mono Legato 关闭。回退力度取共享缓存。', 13, GRAY)
    c.save('mono-key-priority')
    c = Canvas(900, 390)
    c.text(450, 12, 'Unison：Thickness 改变中间声部的位置', 24)
    for panel, voices in enumerate([2, 4, 6]):
        x, width = 70+panel*300, 200
        c.text(x+width/2, 60, str(voices)+' 声', 18, BLUE)
        table = next(t for t in unison['tables'] if t['voices'] == voices)
        for row, thickness in enumerate([0, 1, 9]):
            y = 120+70*row
            c.text(x-34, y-8, 'Off' if thickness == 0 else str(thickness), 12, GRAY)
            c.line(x, y, x+width, y, '#d7e3eb')
            color = [BLUE, TEAL, GOLD][row]
            for coefficient in table['thickness_rows'][thickness]:
                xx = x+(coefficient+8192)*width/16384
                c.line(xx, y-8, xx, y+8, color, 2)
        for v in [-1, 0, 1]:
            xx = x+(v+1)*width/2
            c.text(xx, 286, str(v), 12, GRAY)
        c.text(x+width/2, 310, '分散系数 / 8192', 13, GRAY)
    c.text(450, 355, '各行：Thickness Off、1、9；端点固定，内部位置直接读取固件表。', 13, GRAY)
    c.save('unison-spread')


if __name__ == '__main__':
    main()
