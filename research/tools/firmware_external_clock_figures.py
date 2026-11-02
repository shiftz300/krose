#!/usr/bin/env python3
"""Draw verified external-clock routing and Auto recovery trace."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT


def main():
    r = json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/external-clock-check.json').read_text())
    assert r['passed'] and len(r['auto_trace']) == 1000
    c = Canvas(900, 430)
    c.text(450, 12, '外部时钟：检测来源与推进节拍分开执行', 23)
    c.box(25, 70, 230, 110, '接收 F8 字节', ['更新最后接收时间', '设置“外部时钟存在”'], BLUE)
    c.box(335, 70, 230, 110, '检查来源与端口', ['Ext-MIDI → 端口码 7', 'Ext-USB → 端口码 8'], BLUE)
    c.box(645, 70, 230, 110, '共享节拍计数 +20', ['调用音乐消费者', '24 个脉冲 = 480 tick'], TEAL)
    c.arrow(255, 125, 335, 125)
    c.arrow(565, 125, 645, 125)
    c.box(25, 255, 230, 110, '定时访问检查丢失', ['无新 F8：第 501 次清除', '短等待标记：第 64 次清除'], GOLD)
    c.box(335, 255, 230, 110, 'Auto 来源切换', ['存在：使用外部计数', '消失：恢复内部计数'], GOLD)
    c.box(645, 255, 230, 110, '音源等待队列', ['按新增 tick 扣除剩余拍长', '到期后设置声部就绪标志'], TEAL)
    c.arrow(140, 180, 140, 255, GOLD)
    c.arrow(255, 310, 335, 310, GOLD)
    c.arrow(760, 180, 760, 255, TEAL)
    c.text(450, 395, '时钟存在标志先于端口筛选更新；Auto 可接受 MIDI 与 USB 两路脉冲。', 13, GRAY)
    c.save('external-clock-path')

    c = Canvas(920, 470)
    c.text(460, 10, 'Auto 连续轨迹：外部脉冲停止后恢复内部时钟', 23)
    x, y, w, h = 75, 95, 770, 250
    maximum = max(p['shared_ticks'] for p in r['auto_trace'])
    for value in range(0, maximum+50, 100):
        yy = y+h-value*h/maximum
        c.line(x, yy, x+w, yy, '#e4edf3')
        c.text(x-30, yy-8, str(value), 12, GRAY)
    c.text(95, 68, '累计 tick', 13, GRAY)
    for visit in [0, 21, 252, 500, 753, 1000]:
        xx = x+visit*w/1000
        c.text(xx, y+h+13, str(visit), 12, GRAY)
    c.line(x, y, x, y+h)
    c.line(x, y+h, x+w, y+h)
    prev = (x, y+h)
    for point in r['auto_trace']:
        xx = x+point['visit']*w/1000
        yy = y+h-point['shared_ticks']*h/maximum
        c.line(*prev, xx, yy, TEAL if point['external'] else BLUE, 2)
        if point['pulse']:
            c.line(xx, y+h+2, xx, y+h+7, TEAL, 2)
        prev = (xx, yy)
    for visit, label in [(252, '最后一个 F8'), (753, '恢复内部计数')]:
        xx = x+visit*w/1000
        c.line(xx, y, xx, y+h, GOLD, 1, True)
        c.text(xx, 67, label, 13, GOLD)
    c.text(470, 225, '等待超时期间，节拍计数保持不变', 14, TEAL)
    c.text(460, 387, '定时访问序号；前 252 次访问收到 12 个 F8，每个增加 20 tick', 14, GRAY)
    c.text(460, 422, '原指令连续执行 1,000 次；蓝色为内部来源，绿色为外部来源。', 13, GRAY)
    c.save('external-clock-auto')


if __name__ == '__main__':
    main()
