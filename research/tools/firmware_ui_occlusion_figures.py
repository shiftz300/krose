#!/usr/bin/env python3
"""Draw verified visible-region rectangles from original context output."""
import json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY
from layout import PRODUCT_ROOT as ROOT

def main():
    r=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04/ui-occlusion-check.json').read_text())
    assert r['passed']
    case=next(v for v in r['activation'] if not v['skip_occlusion'] and not v['clipping'] and v['flags']==[0,0] and not v['field8'] and not v['branch'])
    c=Canvas(900,460);c.text(450,15,'重叠对象怎样限制绘制范围',23)
    def rectangle(x,y,box,color,fill):
        left,top,right,bottom=[box[0]*6+x,box[1]*6+y,box[2]*6+x,box[3]*6+y]
        c.draw.rectangle((left*2,top*2,right*2,bottom*2),fill=fill,outline=color,width=2)
        c.svg.append(f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="{fill}" stroke="{color}"/>')
    for x,label in [(35,'对象 A 与后续同级对象'),(480,'原函数生成的可绘制区域')]:
        c.text(x+192,64,label,17,BLUE);rectangle(x,112,(0,0,64,24),GRAY,'#edf3f6')
    rectangle(35,112,(16,4,30,20),GOLD,'#f4e4ce')
    rectangle(35,112,(25,12,50,22),GOLD,'#edcc9d')
    c.text(35+23*6,112+6*6,'B',15,GOLD);c.text(35+39*6,112+15*6,'C',15,GOLD)
    c.text(35+7*6,112+9*6,'A',15,BLUE)
    for box in case['rectangles']:
        rectangle(480,112,box,TEAL,'#dfefed')
    c.arrow(430,185,467,185,BLUE)
    c.text(450,292,f'示例保留 {len(case["rectangles"])} 块矩形、{case["visible_pixels"]} 个像素；遮挡区域不写入。',17,TEAL)
    c.text(450,336,'上下文预分配 8 个矩形槽，绘制结束后全部归还。',15,GRAY)
    c.text(450,375,'检查覆盖原区域链表、矩形切分、像素清除和回收；图中布局为合成场景。',13,GRAY)
    c.save('ui-occlusion-regions')

if __name__=='__main__':main()
