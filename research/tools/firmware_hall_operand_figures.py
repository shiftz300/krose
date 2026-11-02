#!/usr/bin/env python3
"""Draw Hall reference order, without implying DSP audio connections."""
import csv,hashlib,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    source=OUT/'hall-local-operands-check.json';d=json.loads(source.read_text());assert d['passed']
    c=Canvas(1080,560);c.text(540,12,'Hall 四段延迟区间的程序引用顺序',24)
    c.text(540,52,'横轴为原程序项编号；标记来自字段 A，未将它们解释成音频读写指令',14,GRAY)
    left,right=180,1010;width=right-left
    for pc in [0,20,40,60,80,100,120]:
        x=left+pc/120*width;c.line(x,114,x,426,'#e5eef2');c.text(x,438,str(pc),12,GRAY)
    rows=[]
    for line,(start,end,decay,damp) in enumerate([(22,5,31,35),(23,8,32,36),(24,11,33,37),(25,14,34,38)]):
        y=145+80*line;lo,hi=d['initial_constants'][start],d['initial_constants'][end]
        c.text(80,y-15,f'区间 {line+1}',16,BLUE);c.text(80,y+8,f'{lo}—{hi}',12,GRAY);c.line(left,y,right,y,'#cbd9e1')
        for kind,index,color,label in [('end',end,BLUE,'终点'),('decay',decay,TEAL,'衰减'),('damping',damp,GOLD,'阻尼'),('start',start,BLUE,'起点')]:
            uses=[r['pc'] for r in d['items'] if r['a']==index]
            for pc in uses:
                x=left+pc/120*width;c.line(x,y-7,x,y+7,color,4)
                rows.append(dict(line=line+1,kind=kind,local_index=index,program_item=pc,address_or_initial=d['initial_constants'][index]))
            x=left+sum(uses)/len(uses)/120*width;c.text(x,y+12 if kind=='damping' else y-31,label+' '+','.join(map(str,uses)),12,color)
    c.text(540,480,'终点字段先出现，起点字段后出现；本图只记录引用次序。',14,BLUE)
    c.text(540,516,'A/B 的局部索引按槽位平移；扩散、阻尼递推和反馈连线仍需运算语义验证。',13,GRAY)
    c.save('hall-reference-order')
    p=OUT/'hall-reference-order.csv'
    with p.open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),csv_sha256=sha(p),rows=len(rows),
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/hall-reference-order.png',ROOT/'research/docs/architecture/figures/hall-reference-order.svg']])
    (OUT/'hall-reference-order-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered Hall reference-order PNG/SVG and CSV.')
if __name__=='__main__':main()
