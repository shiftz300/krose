#!/usr/bin/env python3
"""Illustrate verified sequencer note format and cross-bar lifetime."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT


def main():
    r = json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/sequence-notes-check.json').read_text())
    assert r['passed'] and r['continuous'][-1]['active'] == 0
    c = Canvas(900, 510)
    c.text(450, 14, '序列器把音符记录转换为 MIDI，并单独登记关音时间', 22)
    for x, w, title, lines in [
        (30, 100, '+0', ['类型 09']), (140, 100, '+1', ['此分支未读']),
        (250, 100, '+2', ['音高']), (360, 100, '+3', ['力度']),
        (470, 190, '+4…+5', ['时长 / 延音值']), (670, 200, '+6…+7', ['起始 tick / 延音值'])]:
        c.box(x, 63, w, 82, title, lines)
    c.arrow(450, 145, 450, 185)
    c.box(285, 185, 330, 87, '顺向播放解码器 · 256810', ['检查位置与轨道开关', '生成 9n 音高 力度'], TEAL)
    c.arrow(285, 227, 200, 227)
    c.box(30, 185, 170, 105, '每轨 64 个关音槽', ['到期 tick、音高、力度', '到期生成 8n 音高 40'], BLUE)
    c.arrow(375, 272, 235, 337)
    c.arrow(525, 272, 665, 337)
    c.box(80, 337, 310, 100, '本机消息队列', ['最多 128 个环形位置', '排空后经过本机 MIDI 开关'], TEAL)
    c.box(510, 337, 310, 100, '外发字节路径', ['240044 → 138178', '同一消息送往两个端口缓冲对象'], GOLD)
    c.text(450, 467, '检查执行原解码、关音、队列与格式化函数；在 MIDI 接收入口和端口缓冲接口截获。', 13, GRAY)
    c.save('sequence-note-path')

    c = Canvas(900, 430)
    c.text(450, 12, '跨小节延音沿用原音符，零时长音符在下一次扫描关音', 21)
    c.text(450, 55, '原顺向调度器的连续执行轨迹 · 4/4，每小节 1920 tick', 14, GRAY)
    x0, x1, x2, x3 = 100, 230, 500, 800
    c.line(x0, 300, 840, 300)
    for x, label in [(x0, '小节 0 / 1800'), (x1, '1801'), (x2, '小节 1 / 0'), (x3, '120')]:
        c.line(x, 100, x, 306, '#dce5eb', 1, True)
        c.text(x, 315, label, 13, GRAY)
    c.text(50, 137, 'C4', 16, BLUE)
    c.line(x0, 150, x3, 150, BLUE, 4)
    c.text(175, 109, 'Note On', 14, BLUE)
    c.text(x2, 174, '延音记录匹配音高与力度', 14, BLUE)
    c.text(x3-20, 109, 'Note Off', 14, BLUE)
    c.text(50, 237, 'D4', 16, TEAL)
    c.line(x0, 250, x1, 250, TEAL, 4)
    c.text(170, 211, '时长 0', 14, TEAL)
    c.text(x1+92, 259, '下一次扫描发送 Note Off', 13, TEAL)
    c.text(450, 364, 'C4：7FFF 延音 → 小节边界转为 7FFE → 续接记录写入结束 tick 120。', 14, GRAY)
    c.text(450, 398, '横向间距为示意；小节与 tick 标注、消息顺序来自检查结果。', 13, GRAY)
    c.save('sequence-note-ties')


if __name__ == '__main__': main()
