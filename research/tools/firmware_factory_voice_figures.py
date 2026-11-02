#!/usr/bin/env python3
"""Illustrate the verified real factory voice chain and overlap weights."""
import csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_limiter_figures import axis,curve
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    d=json.loads((OUT/'factory-voice-chain-check.json').read_text());assert d['passed'] and not d['smoke_only']
    row=next(x for x in d['extra'] if (x['program'],x['oscillator'],x['note'],x['velocity'])==('A011',1,63,105))
    c=Canvas(900,620);c.text(450,13,'一个真实交叉音符如何使用四个声部',24)
    c.text(450,53,'原厂 A011 / OSC1，按键 63、力度 105；选层、分配、区域参数与启动一起执行',13,GRAY)
    c.box(245,95,410,85,'两层各获得 16384 / 32768 权重',['描述符电平 127 × 0.5，整数结果为 63','每层含左右采样，各占两个 TG 槽'],BLUE)
    for slot,x,title in [(0,25,'层 1：区域电平修正 −23'),(1,475,'层 2：区域电平修正 0')]:
        rows=[v for v in row['voices'] if v['slot']==slot];primary=next(v for v in rows if v['pair_type']==1)
        c.arrow(450,180,x+200,230)
        c.box(x,230,400,88,title,[f"主侧中间增益 = {primary['multisample_gain']}",'不同素材的区域修正保留到原增益计算'],GOLD)
        for side,v in enumerate(rows):
            xx=x+210*side;c.arrow(x+200,318,xx+95,370)
            c.box(xx,370,190,130,'主侧' if v['pair_type']==1 else '副侧',[
                f"Multisample {v['multisample']}",f"Sample {v['sample']}",
                f"TG 槽 {v['tg_slot']}",'计算控制状态' if v['pair_type']==1 else '复制主侧控制状态'],TEAL)
    c.text(450,541,'副侧保留自己的采样地址，共享主侧包络、滤波、Mixer 和音量状态。',14,BLUE)
    c.text(450,580,'原 TG 启动字已核对；总线在模拟器边界截获，未生成芯片音频。',12,GRAY)
    c.save('factory-voice-stereo-chain')

    c=Canvas(960,460);c.text(480,12,'原厂交叉层：权重进入真实采样声部',24)
    c.text(480,53,'每个点均执行完整原调用链；折线连接已核对的离散点',13,GRAY)
    names={0:'线性',1:'查表',2:'叠层'}
    for panel,kind in enumerate([0,1,2]):
        rep=d['overlap_representatives'][str(kind)];name=chr(65+rep['program_index']//128)+str(rep['program_index']%128).zfill(3)
        data=[x for x in d['extra'] if x['program']==name and x['oscillator']==rep['osc']+1 and x['note']==63]
        bottom,width=rep['bottom'],rep['width'];x=58+318*panel;c.text(x+115,100,f"{name} / OSC{rep['osc']+1}：{names[kind]}",16,BLUE)
        end=min(127,bottom+width)
        xy=axis(c,x,160,235,175,[(bottom,str(bottom)),(bottom+width/2,str(int(bottom+width/2))),(end,str(end))],
                [(0,'0'),(.5,'0.5'),(1,'1')],lambda v:(v-bottom)/width,lambda v:v)
        for offset,color in [(0,BLUE),(1,TEAL)]:
            points=[]
            for item in data:
                if not bottom<=item['velocity']<=end:continue
                value=next((r['weight'] for r in item['selection'] if r['slot']==rep['slot']+offset),0)
                points.append(xy(item['velocity'],value/32768))
            for a,b in zip(points,points[1:]):c.line(*a,*b,color,2,dash=bool(offset))
        c.text(x+115,372,'力度',13,GRAY)
    c.line(270,417,300,417,BLUE,2);c.text(350,408,'当前层',13,BLUE)
    c.line(535,417,565,417,TEAL,2,True);c.text(615,408,'相邻层',13,TEAL)
    c.text(480,445,'叠层例子的上界为 128，合法力度只到 127；两条权重曲线重合。',12,GRAY)
    c.save('factory-voice-overlaps')

    with (OUT/'factory-voice-chain.csv').open('w',newline='') as out:
        writer=csv.writer(out);writer.writerow(['group','program','oscillator','note','velocity','layer','side','slot','weight','multisample','region','sample',
                                               'layer_level','region_level_correction','multisample_state','region_gain_formula','reverse','pair_type','voice_slot','tg_slot','delay','amp_target','pitch_word','pitch_increment'])
        for group in ['factory','extra']:
            for item in d[group]:
                for v in item['voices']:writer.writerow([group,item['program'],item['oscillator'],item['note'],item['velocity'],
                    *[v[k] for k in ['layer','side','slot','weight','multisample','region','sample','layer_level','region_level_correction','multisample_gain','region_gain_formula',
                                    'reverse','pair_type','voice_slot','tg_slot','delay','amp_target','pitch_word','pitch_increment']]])
    with (OUT/'factory-voice-selection.csv').open('w',newline='') as out:
        writer=csv.writer(out);writer.writerow(['group','program','oscillator','note','velocity','layer','side','slot','weight','pitch','multisample','region','descriptor_valid','attempted'])
        for group in ['factory','extra']:
            for item in d[group]:
                for r in item['selection']:writer.writerow([group,item['program'],item['oscillator'],item['note'],item['velocity'],
                    *[r[k] for k in ['layer','side','slot','weight','pitch','multisample','region','valid','attempted']]])
    print('Rendered two factory voice-chain figures (PNG/SVG), with two source CSV files.')
if __name__=='__main__':main()
