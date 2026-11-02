#!/usr/bin/env python3
"""Show the native reference rules used when imported Programs move."""
import csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    d=json.loads((OUT/'program-relocation-check.json').read_text());assert d['passed']
    c=Canvas(960,620);c.text(480,14,'导入位置改变时，Program 引用怎样移动',24)
    c.text(480,55,'原函数 1F373C：只修改满足条件的编号，完整记录其余字节保持原值',13,GRAY)
    rows=[('用户鼓组','Drum 模式且编号 ≥ 42','新号 = min(57, 旧号 − 42 + 目标起点)',BLUE),
          ('琶音 Pattern','编号 ≥ 1029','新号 = min(1284, 旧号 − 1024 + 目标基数)',TEAL),
          ('鼓轨 / 步进所用 Program','768 ≤ 编号 < 768 + 本次导入数量','新号 = min(1279, 旧号 − 768 + 目标起点)',BLUE)]
    for i,(title,condition,rule,color) in enumerate(rows):
        y=105+108*i;c.box(35,y,280,80,title,[condition],color);c.arrow(315,y+40,355,y+40)
        c.box(355,y,570,80,rule,['未满足条件的引用保留原值'],color)
    selected=[r for r in d['drum_links'] if r['kit_target']==46]
    c.box(80,453,800,80,'Future Synth 四个鼓组：导入起点从 42 移到 46',[
        '原编号：'+ ' / '.join(str(r['stored_kit']) for r in selected),
        '新编号：'+ ' / '.join(str(r['relocated_kit']) for r in selected)+'；前两个仍共用同一编号'],GOLD)
    c.text(480,568,'上限截断可能使多个引用合并；完整文件导入的容量检查与套件放置尚待核对。',13,GRAY)
    c.save('program-reference-relocation')
    with (OUT/'program-relocation-records.csv').open('w',newline='') as out:
        fields=['program','name','kit_target','pattern_target','program_target','changed_offsets','sha256'];w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
        for row in d['records']:w.writerow({k:json.dumps(row[k]) if k=='changed_offsets' else row[k] for k in fields})
    print('Rendered Program relocation PNG/SVG and complete source-record CSV.')
if __name__=='__main__':main()
