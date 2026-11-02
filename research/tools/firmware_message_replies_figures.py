#!/usr/bin/env python3
"""Verified parameter-list ownership and reply handoff across CS/MMI."""
import json
from firmware_runtime_figures import Canvas, BLUE, TEAL, GOLD, GRAY
from layout import PRODUCT_ROOT as ROOT

def main():
    r=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/message-replies-check.json').read_text())
    assert r['passed'] and len(r['handoffs'])==8
    c=Canvas(900,545)
    c.text(450,15,'MMI 复制参数列表后，发送方才回收消息',23)
    c.text(215,66,'任务 2 · CS / 参数发送方',18,BLUE)
    c.text(685,66,'任务 3 · MMI 接收方',18,TEAL)
    c.box(35,105,360,90,'发送变更列表',['类型 9 / 子类型 0 / 命令 12','附带 16 位流水号和列表指针'],BLUE)
    c.box(505,105,360,90,'复制每条记录',['24 字节独立副本','追加到 MMI 待处理列表'],TEAL)
    c.arrow(395,150,505,150)
    c.box(35,255,360,90,'等待命令 13',['按子类型 / 命令 / 流水号匹配','期间继续分派其他事件'],BLUE)
    c.box(505,255,360,90,'原消息改成回复',['类型 8 / 子类型 0 / 命令 13','流水号和载荷指针保持不变'],TEAL)
    c.arrow(215,195,215,255);c.arrow(685,195,685,255)
    c.arrow(505,300,395,300)
    c.box(35,405,360,90,'收到回复并回收',['释放载荷，归还消息节点','原列表随后可清理'],BLUE)
    c.box(505,405,360,90,'后续页面处理',['使用 MMI 自己的记录副本','回调与显示更新继续追踪'],GOLD)
    c.arrow(215,345,215,405);c.arrow(685,345,685,405,GOLD,True)
    c.text(450,515,'已执行原发送、队列、接收分派、复制及回复；任务切换由隔离夹具安排。',13,GRAY)
    c.save('parameter-message-handoff')

if __name__=='__main__':main()
