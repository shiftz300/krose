#!/usr/bin/env python3
"""Illustrate verified release handoff and combined pedal trajectories."""
import csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_limiter_figures import axis,curve
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    d=json.loads((OUT/'pedal-release-flow-check.json').read_text());assert d['passed']
    c=Canvas(900,650);c.text(450,14,'声部释放：即时提交与后续更新',24)
    c.text(450,53,'图示为允许释放、已启动、无等待且保持条件均已解除的普通路径',13,GRAY)
    rows=[(100,'事件当次','释放管理器',['加入可替换队列；可用数保持不变','重新判断 CC66 保持与 CC64 延音']),
          (230,'事件当次','音量先更新并提交',['Amp EG 进入 Release，并推进一次','计算音量目标；读回电平，提交 TG 目标与步长']),
          (360,'第 1 次声部更新','统一准备三类 EG 的释放段',['消耗声部标志 0x04','Pitch / Filter / Amp 重新准备 Release；本次不推进']),
          (490,'第 2 次声部更新','恢复正常控制推进',['推进三类 EG 和两路 LFO','后续刷新、Mixer 与目标计算继续使用原控制链'])]
    for y,label,title,lines in rows:
        c.text(108,y+34,label,14,GRAY);c.box(220,y,620,92,title,lines,TEAL if y==360 else BLUE)
        if y<490:c.arrow(530,y+92,530,y+130)
    c.text(450,618,'所有音频总线访问均在模拟器内截获；本图描述控制顺序。',13,GRAY)
    c.save('pedal-release-handoff')

    rows=[(next(x for x in d['traces'] if (x['auxiliary'],x['special'],x['enabled'],x['sost'])==(0,0,1,s)),color,label)
          for s,color,label in [(0,BLUE,'仅延音踏板'),(1,GOLD,'延音 + 保持踏板')]]
    c=Canvas(900,600);c.text(450,12,'两种踏板共同决定释音起点',24)
    c.text(450,52,'受控普通 OSC：第 16 次松键，第 64 次松延音，第 96 次松保持',13,GRAY)
    for x,color,label in [(275,BLUE,'仅延音踏板'),(640,GOLD,'延音 + 保持踏板')]:
        c.line(x-110,93,x-80,93,color,2);c.text(x+5,84,label,13,color)
    for y,key,title in [(155,'level','音量包络 / 32767'),(375,'amp','音量控制目标 / 32767')]:
        c.text(450,y-35,title,14,GRAY)
        xy=axis(c,95,y,710,135,[(0,'0'),(16,'16'),(64,'64'),(96,'96'),(128,'128'),(191,'191')],
                [(0,'0'),(.5,'0.5'),(1,'1')],lambda v:v/191,lambda v:v)
        for update,label in [(16,'松键'),(64,'松延音'),(96,'松保持')]:
            xx,_=xy(update,0);c.line(xx,y,xx,y+135,GRAY,1,True)
            if y==155:c.text(xx,y-20,label,11,GRAY)
        for row,color,label in rows:
            curve(c,[xy(p['update'],(p['levels'][2] if key=='level' else p['amp'])/32767) for p in row['steps']],color)
    c.text(450,551,'横轴为声部更新次数；保持仍有效时，松开延音踏板不会开始释音。',13,BLUE)
    c.text(450,584,'主机控制量轨迹；未把控制调用次数换算为实际秒数。',12,GRAY)
    c.save('pedal-release-holds')
    with (OUT/'pedal-release-flow.csv').open('w',newline='') as out:
        writer=csv.writer(out);writer.writerow(['auxiliary','runtime_table_B','pedal_enabled','sostenuto','update','cc64','voice_status',
                                               'pitch_stage','filter_stage','amp_stage','pitch_level','filter_level','amp_level','amp_target','aux_level'])
        for row in d['traces']:
            for p in row['steps']:writer.writerow([row['auxiliary'],row['special'],row['enabled'],row['sost'],p['update'],p['cc64'],
                                                   p['voice_status'],*p['stages'],*p['levels'],p['amp'],p['aux_level']])
    print('Rendered two pedal-release figures (PNG/SVG) and one trajectory CSV.')
if __name__=='__main__':main()
