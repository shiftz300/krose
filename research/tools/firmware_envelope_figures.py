#!/usr/bin/env python3
"""Plot verified envelope lifecycles and phase-dependent Time AMS scaling."""
import csv,json,math
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD,PALE
from firmware_limiter_figures import axis,curve
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
COLORS=[BLUE,TEAL,GOLD];NAMES=['Pitch EG','Filter EG','Amp EG']

def main():
    d=json.loads((OUT/'envelopes-check.json').read_text());assert d['passed']
    row=next(v for v in d['lifecycle'] if v['time']==50 and v['curves']==[0,3,7,10])
    c=Canvas(900,520);c.text(450,12,'三类 EG：保持与释放的连续状态',24)
    c.text(450,52,'基础时间索引 50；曲线 0 / 3 / 7 / 10；纵轴为状态电平 / 32767',13,GRAY)
    xy=axis(c,90,145,720,245,[(0,'0'),(64,'64'),(128,'128'),(192,'192'),(255,'255')],[(-1,'−1'),(-.5,'−0.5'),(0,'0'),(.5,'0.5'),(1,'1')],lambda v:v/255,lambda v:(v+1)/2)
    for kind,color in enumerate(COLORS):curve(c,[xy(p['update'],p['eg_levels'][kind]/32767) for p in row['steps']],color)
    for x,name,color in zip([220,450,680],NAMES,COLORS):c.line(x-70,97,x-45,97,color,2);c.text(x+5,88,name,13,color)
    xx=xy(128,0)[0];c.line(xx,126,xx,390,GRAY,1,True);c.text(xx+55,120,'开始释放',12,GRAY)
    c.text(450,433,'控制更新次数；曲线表示 EG 控制状态，未经过 TG 音频处理。',13,GRAY)
    c.text(450,471,'音高和滤波允许负电平；音量包络保持非负并最终归零。',14,BLUE)
    c.text(450,501,'保持状态与结束标志分别比较，不能仅凭段号判断声部结束。',12,GRAY)
    c.save('envelope-lifecycle')

    c=Canvas(900,480);c.text(450,12,'Time AMS：不同包络和阶段使用不同深度',23)
    c.text(450,52,'基础时间索引 50，来源 +4096，强度 +99；纵轴为相对时长（对数坐标）',13,GRAY)
    def y(ratio):return 345-200*math.log2(ratio)/12
    for exponent in [0,6,12]:
        yy=y(2**exponent);c.line(90,yy,820,yy,PALE);c.text(48,yy-8,str(2**exponent)+'×',12,GRAY)
    c.line(90,145,90,345);c.line(90,345,820,345)
    for phase,label in enumerate(['起音','衰减','后段','释放']):
        center=180+195*phase
        for kind,color in enumerate(COLORS):
            item=next(p for p in d['duration_cases'] if (p['amount'],p['source'],p['kind'],p['phase'])==(99,4096,kind,phase))
            base=next(p['duration'] for p in d['duration_cases'] if (p['amount'],p['source'],p['kind'],p['phase'])==(0,4096,kind,phase))
            ratio=item['duration']/base;x=center+(kind-1)*39;yy=y(ratio)
            if ratio==1:c.line(x-7,345,x+7,345,color,3)
            else:c.line(x,345,x,yy,color,15)
            c.text(x,yy-26,str(round(ratio))+'×',11,color)
        c.text(center,370,label,15,GRAY)
    for x,name,color in zip([220,450,680],NAMES,COLORS):c.line(x-70,97,x-45,97,color,2);c.text(x+5,88,name,13,color)
    c.text(450,418,'Pitch EG 的释放段不读取该组 Time AMS；Amp EG 的衰减段采用一倍深度。',13,BLUE)
    c.text(450,454,'其余受测阶段采用两倍深度；108 组来源、强度与阶段组合已核对。',12,GRAY)
    c.save('envelope-time-modulation')
    with (OUT/'envelope-lifecycles.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['time_index','curves','update','release','pitch_level','filter_level','amp_level','pitch_stage','filter_stage','amp_stage','voice_status'])
        for row in d['lifecycle']:
            for p in row['steps']:w.writerow([row['time'],'/'.join(map(str,row['curves'])),p['update'],p['release'],*p['eg_levels'],*p['eg_stages'],p['voice_status']])
    with (OUT/'envelope-time-modulation.csv').open('w',newline='') as out:
        w=csv.DictWriter(out,['amount','source','kind','phase','duration']);w.writeheader();w.writerows(d['duration_cases'])
    with (OUT/'envelope-retriggers.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['threshold','update','source','released','pitch_reset','filter_reset','amp_reset','pitch_stage','filter_stage','amp_stage'])
        for row in d['retriggers']:
            for p in row['steps']:w.writerow([row['threshold'],p['update'],p['source'],p['released'],*p['reset'],*p['stages']])
    print('Rendered two envelope figures (PNG/SVG), with three source CSV files.')
if __name__=='__main__':main()
