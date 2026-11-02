#!/usr/bin/env python3
"""MMI parameter queue selection and downstream callback operations."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT

def main():
    r=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/mmi-parameters-check.json').read_text())
    assert r['passed'] and len(r['integrated'])==3
    c=Canvas(900,550)
    c.text(450,15,'MMI 先判断页面状态，再处理参数变更',23)
    c.box(315,65,270,90,'已复制的变更记录',['参数编号 / 类型 / 新旧值','等待 MMI 主循环处理'],BLUE)
    for x in [165,450,735]:c.arrow(450,155,x,210)
    c.box(25,210,280,110,'本轮延后',['按参数组与索引保留第一条','其余重复记录销毁','处理完后移回原列表'],GOLD)
    c.box(315,210,270,110,'立即处理',['调用界面与参数回调','处理后销毁记录'],TEAL)
    c.box(595,210,280,110,'本轮丢弃',['对象状态不接受该更新','或类型 12 找不到界面对象'],GRAY)
    c.line(450,320,450,343);c.line(450,343,150,343);c.arrow(150,343,150,365)
    c.box(25,365,250,105,'界面对象虚表 +B4',['对象有效且新旧值不同','传入新旧值与范围'],TEAL)
    c.box(325,365,250,105,'参数回调：操作码 9',['传入 MMI / 界面对象','参数编号、类型和新旧值'],BLUE)
    c.box(625,365,250,105,'参数回调：操作码 24',['返回正的 16 位编号时','进入后续通知 13A194'],GOLD)
    c.arrow(275,418,325,418);c.arrow(575,418,625,418)
    c.text(450,503,'连续延后例子：输入 11 → 22 → 33 → 44，保留第一条 11；解除阻塞后再处理。',14,GRAY)
    c.save('mmi-parameter-update')

if __name__=='__main__':main()
