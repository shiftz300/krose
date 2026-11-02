#!/usr/bin/env python3
"""Show verified EQ references alongside clearly labeled host hypotheses."""
import csv,json,math
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GOLD,GRAY,PALE
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def write_csv(path,rows):
    with path.open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    source=OUT/'eq-b2-program-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    host=d['host_candidates'];case=next(r for r in host['rows'] if (r['program'],r['slot'])==('D100','IFX2'))
    curve=next(s['curves'] for s in case['static'] if s['weight']==.5)
    c=Canvas(1200,990);c.text(600,15,'四段 EQ：B2 双端点引用与动态算法缺口',24)
    c.text(600,58,'原七槽初始化、331 个原厂槽位及 6620 次参数回调已核对；以下程序结构仅表示编码引用。',14,GRAY)
    c.box(65,110,495,128,'基础系数：常数 12–21',['左侧引用项 14 / 15 / 17–24','右侧引用项 65 / 66 / 68–75','左 B 字段：7、8、9、11、12、768'],BLUE)
    c.box(640,110,495,128,'调制端点：常数 22–31',['左侧引用项 25–34','右侧引用项 76–85','左 B 字段：7、8、9、10、14、15'],TEAL)
    c.text(600,264,'两侧有 46 对精确镜像：普通 B 字段偏移 +30，输入选择 32 → 33。',14,GRAY)
    c.text(600,309,'主机候选比较，原 DSP 未执行',20,GOLD)
    c.text(600,344,'D100 / IFX2 · B2 增益端点 0 / −9.5 dB · 固定权重 0.5',14,GRAY)
    left,right,top,bottom=130,1110,400,675
    c.text(92,371,'dB',13,GRAY)
    for value in [-10,-5,0]:
        y=bottom-(value+11)/12*(bottom-top);c.line(left,y,right,y,PALE);c.text(92,y-8,str(value),13,GRAY)
    c.line(left,top,left,bottom);c.line(left,bottom,right,bottom)
    for hz in [20,100,1000,10000,20000]:
        x=left+math.log(hz/20,1000)*(right-left);c.line(x,top,x,bottom,PALE);c.text(x,bottom+12,str(hz),12,GRAY)
    for key,color in [('parallel_db',BLUE),('coefficient_db',TEAL)]:
        points=[(left+math.log(row['hz']/20,1000)*(right-left),bottom-(row[key]+11)/12*(bottom-top)) for row in curve]
        for a,b in zip(points,points[1:]):c.line(*a,*b,color,2)
    c.text(600,718,'频率 / Hz；曲线只描述两种候选在 48 kHz 主机定义下的频响。',13,GRAY)
    c.line(220,765,254,765,BLUE,3);c.text(385,755,'两端点滤波后混合输出',14,BLUE)
    c.line(655,765,689,765,TEAL,3);c.text(825,755,'先混合系数，再运行单滤波器',14,TEAL)
    c.text(600,809,'约 1964 Hz 处相差 2.025 dB；该差值没有被计为原机误差或已恢复的音频结果。',14,GOLD)
    c.text(600,851,'61 个不同端点槽位：50 个两端非负、8 个负/非负混合、3 个两端为负。',14,GRAY)
    c.text(600,895,'仍未知：A/B 的读写与流水线、局部 A50/51 的作用、权重平滑、混合及定点舍入。',14,GRAY)
    c.text(600,942,'No Effect 的常数 0：IFX 初始化为 8388607，MFX 为 0；这里只确认控制层差异。',13,GRAY)
    c.save('eq-b2-program')
    program=[dict(pc=r['pc'],visible48=r['visible48'],a=r['a'],b=r['b'],c=r['c'],low=r['low'],upper=r['upper'],format=r['format'],flag2=int(r['flag2'])) for r in d['items']]
    responses=[dict(program=r['program'],slot=r['slot'],gain=r['gain'],other_gain=r['other_gain'],category=r['category'],weight=s['weight'],**v) for r in host['rows'] for s in r['static'] for v in s['curves']]
    dynamic=max(host['rows'],key=lambda r:r['dynamic_maximum_difference'])
    frames=[dict(program=dynamic['program'],slot=dynamic['slot'],frame=i,weight=w,input_left=host['input'][i][0],input_right=host['input'][i][1],
        parallel_left=dynamic['dynamic_parallel'][i][0],parallel_right=dynamic['dynamic_parallel'][i][1],coefficient_left=dynamic['dynamic_coefficient'][i][0],coefficient_right=dynamic['dynamic_coefficient'][i][1]) for i,w in enumerate(host['weights'])]
    paths=[OUT/'eq-b2-program-items.csv',OUT/'eq-b2-candidate-responses.csv',OUT/'eq-b2-candidate-dynamic.csv']
    for p,rows in zip(paths,[program,responses,frames]):write_csv(p,rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},rows=[len(program),len(responses),len(frames)],
        csv=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in paths],
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/eq-b2-program.png',ROOT/'research/docs/architecture/figures/eq-b2-program.svg']])
    (OUT/'eq-b2-program-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,rows=result['rows'])))
if __name__=='__main__':main()
