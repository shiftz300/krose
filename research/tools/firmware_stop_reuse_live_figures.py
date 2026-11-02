#!/usr/bin/env python3
"""Plot complete portable stop/reuse trajectories and their immutable prefixes."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD,PALE
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    source=OUT/'stop-reuse-live-check.json';d=json.loads(source.read_text())
    assert d['passed'] and not d['smoke_only'] and d['portable_continuity_complete']
    assert d['counts']['traces']==96 and d['counts']['updates']==4608
    pairs=[((0,0),(0,61),'A000 → A061'),((2,1),(0,61),'C001 → A061'),((5,36),(0,0),'F036 → A000'),
        ((5,42),(0,0),'F042 → A000'),((10,0),(20,0),'GM 钢琴 → GM 鼓组'),((20,0),(10,0),'GM 鼓组 → GM 钢琴')]
    c=Canvas(1180,900);c.text(590,14,'关音后继续演奏：96 条轨迹完整跑通',24)
    c.text(590,54,'每条 48 次更新；原指令使用私有可写零页，主机适配保留零页未映射。',14,GRAY)
    c.line(390,92,420,92,BLUE,10);c.text(510,82,'旧检查已完成',14,BLUE)
    c.line(650,92,680,92,TEAL,10);c.text(790,82,'本轮继续完成',14,TEAL)
    for i,(first,new,label) in enumerate(pairs):
        traces=[t for t in d['traces'] if tuple(t['old'])==first and tuple(t['new'])==new];assert len(traces)==16
        previous=sum(t['previous_prefix_updates'] for t in traces);total=sum(len(t['steps']) for t in traces);assert total==768
        y=139+42*i;left=330;right=990;split=left+(right-left)*previous/total
        c.text(163,y-9,label,16,BLUE);c.line(left,y,split,y,BLUE,12)
        if split<right:c.line(split,y,right,y,TEAL,12)
        c.text(1080,y-9,f'{previous} → {total}',15,TEAL)
    c.text(590,402,'每行：2 种关音 × 4 种踏板组合 × 2 个模式；横条为完成的更新次数。',13,GRAY)
    selected=[next(t for t in d['traces'] if t['old']==[0,0] and t['new']==[0,61] and t['controller']==cc and t['pedals']==3 and t['mode']==3) for cc in [120,123]]
    c.text(590,449,'同一换音流程：强停立即回收，普通释放保留声部状态',19,BLUE)
    left,right,top,bottom=120,1080,505,720
    maximum=max(1,max(len(s['state']['voices']) for t in selected for s in t['steps']))
    for n in range(maximum+1):
        y=bottom-(bottom-top)*n/maximum;c.line(left,y,right,y,PALE);c.text(90,y-8,str(n),12,GRAY)
    c.line(left,top,left,bottom);c.line(left,bottom,right,bottom)
    c.text(89,478,'声部数',13,GRAY)
    for tick in [0,8,12,20,24,32,36,40,47]:
        x=left+(right-left)*tick/47;c.text(x,bottom+9,str(tick),12,GRAY)
    c.text(590,759,'管理器更新序号（非实测时间）',13,GRAY)
    for t,color in zip(selected,[TEAL,GOLD]):
        points=[(left+(right-left)*s['update']/47,bottom-(bottom-top)*len(s['state']['voices'])/maximum) for s in t['steps']]
        for a,b in zip(points,points[1:]):c.line(*a,b[0],a[1],color,2);c.line(b[0],a[1],*b,color,2)
    c.line(310,491,340,491,TEAL,3);c.text(415,481,'CC120',14,TEAL)
    c.line(670,491,700,491,GOLD,3);c.text(775,481,'CC123',14,GOLD)
    c.text(590,801,'0/12：选定关音；8：松两踏板；20/36：新起音；24/40：松键；32：统一 CC120。',13,GRAY)
    c.text(590,837,'下图取 A000 → A061、模式 3、两踏板开启；显示分配状态，不代表音频电平。',13,GRAY)
    c.text(590,872,'全部状态与 TG I/O 对照通过；实际声音、耗尽抢占及 Mono/Unison 组合仍待验证。',13,GRAY)
    c.save('stop-reuse-live')
    rows=[]
    for t in d['traces']:
        for s in t['steps']:
            rows.append(dict(old_bank=t['old'][0],old_program=t['old'][1],new_bank=t['new'][0],new_program=t['new'][1],
                controller=t['controller'],pedals=t['pedals'],mode=t['mode'],source=t['source'],update=s['update'],
                previously_completed=s['update']<t['previous_prefix_updates'],allocated_voices=len(s['state']['voices']),
                available=s['state']['available'],commits=len(s['commits'])))
    csvfile=OUT/'stop-reuse-live.csv'
    with csvfile.open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    assert len(rows)==4608
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),
        additional_helpers={'firmware_midi_program_load.py':sha(ROOT/'research/tools/firmware_midi_program_load.py')},csv_sha256=sha(csvfile),rows=len(rows),
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/stop-reuse-live.png',ROOT/'research/docs/architecture/figures/stop-reuse-live.svg']])
    (OUT/'stop-reuse-live-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered stop/reuse live PNG/SVG and 4608-row CSV.')
if __name__=='__main__':main()
