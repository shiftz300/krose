#!/usr/bin/env python3
"""Show sensitivity to explicit loop hypotheses, not measured TG error."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD,PALE
from firmware_program_relocation import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    source=OUT/'pcm-loop-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only'] and not d['TG_loop_state_policy_verified']
    c=Canvas(1180,850);c.text(590,16,'压缩循环：历史状态改变，候选 PCM 也会改变',24)
    c.text(590,58,'下图比较模型假设；没有测量 TG 输出，也没有确定芯片采用哪一种策略。',14,GRAY)
    for x,label in zip([160,470,740,1000],['来源 / 区间数','含导出末帧：有差异','去掉末帧：有差异','最大 RMS 差（去末帧）']):c.text(x,108,label,14,GRAY)
    labels={'ROM':'板载 ROM','EXPCM001':'OASYS Piano','EXPCM002':'E.P. Collection','EXPCM004':'Future Synth'}
    for i,library in enumerate(['ROM','EXPCM001','EXPCM002','EXPCM004']):
        a,b=[next(r for r in d['groups'] if r['library']==library and r['excluded_end_frames']==n) for n in [0,1]];y=152+44*i
        for x,value in zip([160,470,740,1000],[f"{labels[library]} / {a['samples']}",str(a['different_pcm24_samples']),str(b['different_pcm24_samples']),f"{b['maximum_rms_difference']:.5f}"]):c.text(x,y,value,15,BLUE)
        c.line(40,y+30,1140,y+30,PALE)
    c.text(590,342,'“有差异”为首次重复循环的 PCM24 比较；不直接表示可闻差异。RMS 以满幅为 1。',13,GRAY)
    w=d['witness'];c.text(590,392,f"最大敏感度候选：{w['library']} 样本 {w['sample']}，保留完整导出末端",18,BLUE)
    values=[v/2**31 for v in w['baseline_prefix']];other=[v/2**31 for v in w['carry_prefix']];assert len(values)==len(other)>1
    left,right,top,bottom=110,1090,460,660
    def xx(i):return left+(right-left)*i/(len(values)-1)
    def yy(v):return (top+bottom)/2-v*(bottom-top)/2
    for v in [-1,-.5,0,.5,1]:c.line(left,yy(v),right,yy(v),PALE);c.text(70,yy(v)-7,str(v),12,GRAY)
    c.line(left,top,left,bottom);c.line(left,bottom,right,bottom)
    for series,color in [(values,BLUE),(other,GOLD)]:
        points=[(xx(i),yy(v)) for i,v in enumerate(series)]
        for a,b in zip(points,points[1:]):c.line(*a,*b,color,2)
    for i in [0,32,64,96,len(values)-1]:c.text(xx(i),bottom+9,str(i),12,GRAY)
    c.text(590,703,'第一次重复循环内的源帧序号；纵轴为重建幅度 / 2^31',13,GRAY)
    c.line(260,747,300,747,BLUE,2);c.text(420,737,'恢复循环前历史',14,BLUE)
    c.line(690,747,730,747,GOLD,2);c.text(860,737,'沿用末端历史',14,GOLD)
    c.text(590,786,'两种候选采用同一份压缩字节、系数和原反馈算术，差别仅在循环历史。',14,GRAY)
    c.text(590,821,'最大敏感度案例用于展示约束，不能作为普通音色或原机误差的估计。',13,GRAY);c.save('pcm-loop-hypotheses')
    rows=[]
    for r in d['rows']:
        for cut in r['cuts']:
            for cycle in cut['cycles']:
                rows.append(dict(library=r['library'],sample=r['sample'],flags=r['flags'],frames=r['frames'],loop=r['loop'],excluded_end_frames=cut['excluded_end_frames'],loop_frames=cut['loop_frames'],cycle=cycle['cycle'],
                    different_pcm24_frames=cycle['different_pcm24_frames'],max_abs_q31_difference=cycle['max_abs_q31_difference'],rms_difference=cycle['rms_difference']))
    csvfile=OUT/'pcm-loop-model-differences.csv'
    with csvfile.open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),additional_helpers={'firmware_program_relocation.py':sha(ROOT/'research/tools/firmware_program_relocation.py')},csv_sha256=sha(csvfile),rows=len(rows),images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/pcm-loop-hypotheses.png',ROOT/'research/docs/architecture/figures/pcm-loop-hypotheses.svg']])
    (OUT/'pcm-loop-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered loop hypotheses and20436-row CSV.')
if __name__=='__main__':main()
