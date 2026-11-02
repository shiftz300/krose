#!/usr/bin/env python3
"""Render stage02 evidence diagrams to matching SVG and high-resolution PNG."""
import html
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from layout import PRODUCT_ROOT as ROOT

DOC=ROOT/'research/docs/architecture/figures'
DATA=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage02'
INK='#18354a';BLUE='#265d82';TEAL='#237b78';GRAY='#647784';GOLD='#a66b27';PALE='#edf3f6'
class Canvas:
    def __init__(self,w,h):
        self.w,self.h=w,h;self.image=Image.new('RGB',(w*2,h*2),'white');self.draw=ImageDraw.Draw(self.image)
        self.svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="100%" height="100%" fill="white"/>']
    def line(self,x1,y1,x2,y2,color=GRAY,width=1,dash=False):
        self.svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"'+(' stroke-dasharray="5 4"' if dash else '')+'/>')
        if dash:
            n=max(1,int(math.hypot(x2-x1,y2-y1)/5))
            for i in range(0,n,2):self.draw.line(tuple(v*2 for v in (x1+(x2-x1)*i/n,y1+(y2-y1)*i/n,x1+(x2-x1)*min(i+1,n)/n,y1+(y2-y1)*min(i+1,n)/n)),fill=color,width=width*2)
        else:self.draw.line((x1*2,y1*2,x2*2,y2*2),fill=color,width=width*2)
    def text(self,x,y,s,size=14,color=INK):
        font=ImageFont.truetype('/System/Library/Fonts/STHeiti Light.ttc',size*2,index=0)
        self.draw.text((x*2,y*2),s,font=font,fill=color,anchor='mt')
        self.svg.append(f'<text x="{x}" y="{y+size}" text-anchor="middle" font-family="Heiti SC, sans-serif" font-size="{size}" fill="{color}">{html.escape(s)}</text>')
    def box(self,x,y,w,h,title,lines,color=BLUE):
        self.draw.rounded_rectangle((x*2,y*2,(x+w)*2,(y+h)*2),radius=10,outline=color,width=2)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="white" stroke="{color}"/>')
        self.text(x+w/2,y+12,title,16,color)
        for i,s in enumerate(lines):self.text(x+w/2,y+40+20*i,s,12,GRAY)
    def arrow(self,x1,y1,x2,y2,color=GRAY,dash=False):
        self.line(x1,y1,x2,y2,color,1,dash);angle=math.atan2(y2-y1,x2-x1)
        for d in [-.45,.45]:self.line(x2,y2,x2-8*math.cos(angle+d),y2-8*math.sin(angle+d),color)
    def save(self,name):
        DOC.mkdir(parents=True,exist_ok=True);self.image.save(DOC/(name+'.png'))
        (DOC/(name+'.svg')).write_text('\n'.join(self.svg+['</svg>']))


def main():
    checks=json.loads((DATA/'note-layers-check.json').read_text());assert checks['passed']
    c=Canvas(760,540);c.text(380,14,'一个音符怎样进入音源',23)
    cells=[(20,65,'MIDI 预处理',['状态分类 / 移调','零力度转换为 Note Off']),
           (275,65,'通道与音色',['16 通道 / 音色开关','键区与力度区筛选']),
           (530,65,'PCM 振荡器',['虚表 +0x14 调用','选择参与发声的 OSC']),
           (530,220,'力度层选择',['四个候选层，最多取两个','计算交叉淡化权重']),
           (275,220,'声部分配',['每层占 1 或 2 个槽','强制分配 / 候选替换']),
           (20,220,'立体声配对',['按 TG 槽号排序','记录双方指针与配对类型']),
           (20,375,'延迟启动',['剩余时间 / 访问次数','到期后设置就绪标志']),
           (275,375,'TG 控制入口',['参数初始化与寄存器写入','本次在函数边界截获']),
           (530,375,'TG 音频执行',['采样 / 滤波 / 效果','DSP 指令语义仍待恢复'])]
    for i,(x,y,title,lines) in enumerate(cells):c.box(x,y,210,105,title,lines,GOLD if i>=7 else BLUE)
    for a,b in [(0,1),(1,2),(3,4),(4,5),(6,7),(7,8)]:
        x,y=cells[a][:2];xx,yy=cells[b][:2]
        if xx>x:c.arrow(x+210,y+52,xx,y+52,GOLD if b>=7 else GRAY,b>=7)
        else:c.arrow(x,y+52,xx+210,y+52)
    c.arrow(635,170,635,220);c.arrow(125,325,125,375)
    c.text(380,501,'图示汇总已恢复的控制关系；TG 启动与音频执行尚未连通验证。',13,GRAY)
    c.save('note-runtime-flow')
    table=checks['results']['helpers']['curve_table']
    def shape(x):
        if x>=32768:return x
        i,f=divmod(x,256);return table[i]+((table[i+1]-table[i])*f>>8)
    c=Canvas(760,380);c.text(380,12,'同一力度交叉区的三种权重',23)
    for k,title in enumerate(['线性（曲线 0）','查表（曲线 1）','叠层（曲线 2）']):
        x=48+k*250;y=90;w=180;h=190
        c.text(x+w/2,55,title,17)
        c.line(x,y,x,y+h);c.line(x,y+h,x+w,y+h)
        for t,label in [(0,'0'),(.5,'0.5'),(1,'1')]:
            c.line(x,y+h-t*h,x+w,y+h-t*h,PALE);c.text(x-18,y+h-t*h-7,label,11,GRAY)
        for v in [70,76,82]:c.text(x+(v-70)/12*w,y+h+10,str(v),11,GRAY)
        c.text(x+w/2,y+h+31,'输入力度',12,GRAY)
        points=[[],[]]
        for v in range(70,83):
            t=(v-70)*32768//12
            gains=[t,32768-t] if k==0 else ([shape(t),shape(32768-t)] if k==1 else [32768,32768 if v<82 else 0])
            for side,gain in enumerate(gains):points[side].append((x+(v-70)/12*w,y+h-gain/32768*h))
        for side,color in enumerate([BLUE,TEAL]):
            for a,b in zip(points[side],points[side][1:]):c.line(*a,*b,color,2,dash=(k==2 and side==1 and b==points[side][-1]))
    c.line(180,350,210,350,BLUE,2);c.text(253,341,'进入层',13,BLUE)
    c.line(330,350,360,350,TEAL,2);c.text(403,341,'退出层',13,TEAL)
    c.text(595,341,'窗口：70 ≤ 力度 < 82',13,GRAY)
    c.save('velocity-crossfade')
    print(DOC/'note-runtime-flow.png');print(DOC/'velocity-crossfade.png')
if __name__=='__main__':main()
