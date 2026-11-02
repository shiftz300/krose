#!/usr/bin/env python3
"""Show stop/reuse conditions, zero-page probes and portable-list equivalence."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD,PALE
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    source=OUT/'stop-reuse-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only'] and d['portable_unlink_verified']
    rows=[];labels=[('none','不停止'),('cc123','CC123 释放'),('cc120','CC120 强停'),('timbre','音色强停'),('osc','OSC 强停'),('list','列表强停'),('slots','逐槽强停')]
    c=Canvas(1180,770);c.text(590,12,'硬停后复用：失败条件与主机适配',24)
    c.text(590,52,'私有 32 槽环境；六类音色、两模式、四力度。用例计数不表示实机发生率。',14,GRAY)
    left,right=320,1000;scale=(right-left)/48
    for n in [0,24,48]:
        x=left+n*scale;c.line(x,105,x,400,'#dce5eb');c.text(x,410,str(n),12,GRAY)
    for i,(action,label) in enumerate(labels):
        cases=[x for x in d['baseline'] if x['action']==action];faults=sum(bool(x['reuse_fault']) for x in cases);assert len(cases)==48
        y=130+40*i;c.text(150,y-9,label,16,BLUE);c.line(left,y,right,y,PALE,14)
        if faults:c.line(left,y,left+faults*scale,y,GOLD,14)
        c.text(1080,y-9,f'{faults} / 48',15,GOLD if faults else TEAL)
        rows.append(dict(group='native_baseline',name=action,cases=48,faults=faults,returned=48-faults))
    c.text(590,443,'橙色为重新申请时触及未映射 0/4 的数量；对照与五层原停止入口分别核对。',13,GRAY)
    for x,title,lines,color in [(40,'原字段 + 未映射零页',['成对声部的空节点再次摘除','120 组在 0/4 处停止'],GOLD),
            (420,'原字段 + 可写零页',['2 / 2 起音返回，仍写 0/4','模拟页前两条向量指令清零'],GOLD),
            (800,'主机空节点适配',['24 / 24 状态及 I/O 一致','保留配对字段，省略空写入'],TEAL)]:c.box(x,487,340,112,title,lines,color)
    c.text(590,635,'C001 → A061：先复用槽 2/3，第三个新音符到旧配对槽时也复现。',15,BLUE)
    c.text(590,681,'主机适配只把已为空的节点摘除视为空操作；受测其余状态与原指令一致。',14,TEAL)
    c.text(590,727,'实机零页映射仍待确定；适配仅在研究代码验证，未修改产品或原固件。',13,GRAY);c.save('stop-reuse-boundaries')
    for name in ['clear_type','clear_partner','clear_both']:
        cases=[x for x in d['counterfactual'] if x['perturbation']==name];rows.append(dict(group='counterfactual',name=name,cases=len(cases),faults=0,returned=len(cases)))
    rows.extend([dict(group='zero_page',name='private_rw',cases=len(d['zero_page']),faults=0,returned=len(d['zero_page'])),
        dict(group='portable',name='skip_empty_unlink',cases=len(d['portable']),faults=0,returned=len(d['portable'])),
        dict(group='queue',name='third_note',cases=len(d['queued']),faults=len(d['queued']),returned=0)])
    csvfile=OUT/'stop-reuse-summary.csv'
    with csvfile.open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    assert len(rows)==13
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},csv_sha256=sha(csvfile),rows=len(rows),
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/stop-reuse-boundaries.png',ROOT/'research/docs/architecture/figures/stop-reuse-boundaries.svg']])
    (OUT/'stop-reuse-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered stop/reuse PNG/SVG and 13-row evidence CSV.')
if __name__=='__main__':main()
