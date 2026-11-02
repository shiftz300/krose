#!/usr/bin/env python3
"""UI tree order and refresh control diagrams backed by execution results."""
import json
import hashlib
from PIL import Image
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY
from layout import PRODUCT_ROOT as ROOT

def main():
    base=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
    tree=json.loads((base/'ui-tree-check.json').read_text())
    refresh=json.loads((base/'ui-refresh-check.json').read_text())
    assert tree['passed'] and refresh['passed']
    assert tree['ring']==[0,1,4,5,2,6,3]
    assert next(r for r in tree['search'] if r['order']==1 and r['mask']==0)['visited']==[3,6,2,5,4,1,0]
    c=Canvas(880,530);c.text(440,15,'同一棵对象树，两种处理顺序',23)
    positions={'R':(440,78),'A':(180,190),'B':(500,190),'C':(735,190),'D':(90,302),'E':(270,302),'F':(500,302)}
    for parent,child in [('R','A'),('R','B'),('R','C'),('A','D'),('A','E'),('B','F')]:
        x,y=positions[parent];xx,yy=positions[child];c.arrow(x,y+55,xx,yy)
    for name,(x,y) in positions.items():c.box(x-55,y,110,55,name,[],TEAL if name=='C' else BLUE)
    c.text(440,389,'参数查找：C → F → B → E → D → A → R',20,TEAL)
    c.text(440,433,'整页刷新：R → A → D → E → B → F → C',20,BLUE)
    c.text(440,482,'查找遇到第一个匹配对象即返回；图中节点来自合成检查树。',14,GRAY)
    c.save('ui-tree-order')
    c=Canvas(900,590);c.text(450,15,'界面对象怎样进入绘制',23)
    c.box(300,65,300,75,'整页环 / 局部子树',['刷新入口 DE344，模式固定为 3'],BLUE)
    c.arrow(450,140,450,177)
    c.box(300,177,300,95,'有效性与矩形判断',['对象索引 / 标志 / 有效面积','裁剪开启时检查矩形交集'],TEAL)
    c.arrow(300,225,175,300);c.arrow(600,225,725,300)
    c.box(35,300,280,110,'暂不绘制',['全局绘制开关关闭 → 状态 1','对象不可见 → 保留 1 或设 2'],GOLD)
    c.box(585,300,280,110,'立即分派绘制',['全局开关打开且对象可见','调用 DCFF4，再设状态 2'],TEAL)
    c.arrow(725,410,725,451)
    c.box(465,451,400,95,'绘制接收者',['背景 → 对象回调 → 虚表 +2C','元素绘制 EFED4 → 标志附加绘制'],BLUE)
    c.text(235,466,'本章已验证遍历、裁剪、状态和调用顺序。',13,GRAY)
    c.text(235,496,'接收者在边界记录调用，像素主体待恢复。',13,GRAY)
    c.save('ui-refresh-path')
    result=json.loads((base/'ui-bitmap-check.json').read_text())
    raw=(base/'ui-bitmap-pattern-sample.bin').read_bytes()
    assert result['passed'] and hashlib.sha256(raw).hexdigest()==result['sample']['sha256']
    c=Canvas(820,390);c.text(410,15,'原固件图案操作：缓冲位的变化',23)
    raster=Image.new('RGB',(240,64),'#edf3f6')
    c.svg.append('<rect x="50" y="65" width="720" height="192" fill="#edf3f6"/>')
    for y in range(64):
        for x in range(240):
            if raw[y*30+x//8]&(128>>(x%8)):
                raster.putpixel((x,y),(38,93,130))
                c.svg.append(f'<rect x="{50+3*x}" y="{65+3*y}" width="3" height="3" fill="{BLUE}"/>')
    c.image.paste(raster.resize((1440,384),Image.Resampling.NEAREST),(100,130))
    for i,title in enumerate(['覆盖','清位','置位 2','置位 3','异或']):c.text(50+3*(26+46*i),270,title,17,BLUE)
    c.text(410,315,'先写相同底纹，再叠加八行图案；深色 = 存储位 1，浅色 = 存储位 0。',14,GRAY)
    c.text(410,346,'240 × 64 原缓冲放大 3 倍。合成原语示例，未重建原厂页面。',13,GRAY)
    c.save('ui-bitmap-operations')

if __name__=='__main__':main()
