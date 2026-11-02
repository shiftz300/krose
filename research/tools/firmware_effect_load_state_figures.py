#!/usr/bin/env python3
"""Show effect constant-bank clearing and the verified commit phases."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY,PALE
from firmware_voice_lfo import OUT
from layout import PRODUCT_ROOT as ROOT

def sha(p):
 import hashlib
 return hashlib.sha256(p.read_bytes()).hexdigest()
def exports(d):
 def flat(r):return {k:r[k] for k in ['effect','slot','buffered','units','code_count','initial_count','zero_tail','context_before_flush','writes_sha256','cpu_constants_sha256','cpu_program_container_sha256','uploaded_constants_sha256','uploaded_visible_program_sha256']}
 return [flat(r) for r in d['rows']],[dict(sequence_slot=t['slot'],step=i,**flat(r)) for t in d['sequences'] for i,r in enumerate(t['steps'])]
def main():
 source=OUT/'effect-load-state-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
 c=Canvas(1200,800);c.text(600,16,'效果加载：常数清零，程序尾部保留',25)
 c.text(600,60,'原选择块按代码项数分配：≤124 项占 1 单位，>124 项占 2 单位；每单位 80 个常数字。',15,GRAY)
 c.box(45,110,315,108,'复制与清零',['复制 N 项代码和 K 个初始常数','常数 K…80U−1 清零'],BLUE)
 c.box(445,110,315,108,'缓冲状态',['代码脏区 0…N−1','常数脏区 0…80U−1'],TEAL)
 c.box(845,110,310,108,'原提交函数',['常数每包最多 32 字','代码每包最多 16 项'],BLUE)
 c.arrow(360,164,445,164);c.arrow(760,164,845,164)
 c.text(600,262,'Hall → EQ → No Effect：单单位常数区的连续加载前缀',20)
 left,right=220,1120;w=right-left
 for x in [0,20,40,60,80]:
  xx=left+w*x/80;c.line(xx,325,xx,576,PALE);c.text(xx,591,str(x),13,GRAY)
 for y,name,count in [(360,'Hall',61),(440,'P4EQ',50),(520,'No Effect',1)]:
  c.text(116,y-8,name,18,BLUE)
  c.line(left,y,left+w*count/80,y,BLUE,30);c.line(left+w*count/80,y,right,y,TEAL,30)
  if count>1:c.text(left+w*count/160,y-7,f'{count} 个原始常数',14,'white')
  c.text(left+w*(count+80)/160,y-7,f'{80-count} 个零',14,'white')
  if count==1:c.text(left+12,551,'首字由初始表复制；槽位专用初始化另行处理',12,GRAY)
 x=left+w*51/80;c.arrow(x,408,x,425,GOLD);c.text(x,382,'A50/51：加载为 0',14,GOLD)
 c.text(600,632,'横轴为局部常数字编号；此图只表示上传数据，不推断 DSP 的动态状态或音频结果。',14,GRAY)
 q=d['counts'];c.text(600,676,f'{q["effects"]} 项独立程序 · {q["loads"]} 次加载 · 7 组连续序列 / 21 次加载',16,TEAL)
 c.text(600,720,'13 项零代码变体排除；双槽测试起点 0–3、5，单槽测试 0–6。',14,GRAY)
 c.text(600,761,'程序尾部保持旧值；未执行 DSP 运算，未确定数据 RAM、平滑算法或可听切换瞬态。',14,GOLD)
 c.save('effect-load-state')
 rows=exports(d);paths=[OUT/('effect-load-state-'+n+'.csv') for n in ['loads','sequences']]
 for p,data in zip(paths,rows):
  with p.open('w',newline='') as f:
   writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
 result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),additional_helpers={'firmware_voice_lfo.py':sha(ROOT/'research/tools/firmware_voice_lfo.py')},rows=list(map(len,rows)),csv=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in paths],images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures'/('effect-load-state.'+ext) for ext in ['png','svg']]])
 (OUT/'effect-load-state-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,rows=result['rows'])))
if __name__=='__main__':main()
