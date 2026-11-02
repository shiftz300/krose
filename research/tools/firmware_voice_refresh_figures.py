#!/usr/bin/env python3
"""Plot verified native update/commit cadence and smoothing coefficients."""
import csv,json,math
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,PALE
from firmware_limiter_figures import axis,curve
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def fill(c,x,y,width,height,color):
    c.draw.rectangle((x*2,y*2,(x+width)*2,(y+height)*2),fill=color)
    c.svg.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{color}"/>')

def main():
    d=json.loads((OUT/'voice-refresh-check.json').read_text());assert d['passed'] and not d['smoke_only']
    row=next(x for x in d['traces'] if (x['program'],x['oscillator'],x['batch'])==('A011',1,3));active={v['voice_slot'] for v in row['initial']['voices']}
    c=Canvas(900,550);c.text(450,12,'声部推进与 TG 提交分批运行',24)
    c.text(450,53,'原厂 A011 / OSC1：四个声部，八槽池；每批 3 个，从槽 7 开始',13,GRAY)
    for x,color,label in [(280,TEAL,'格子上半：推进入口'),(660,BLUE,'格子下半：TG 提交')]:
        fill(c,x-130,94,24,10,color);c.text(x+5,88,label,13,color)
    c.text(480,127,'刷新周期编号',13,GRAY)
    previous=row['initial_cursor']
    for step in row['steps'][:16]:
        update=step['update'];advanced=set(range(previous,min(previous+row['batch'],8)));previous=step['cursor_advance']
        committed={x['voice'] for x in step['commits']};x=160+38*update;c.text(x+18,151,str(update),11,GRAY)
        for slot in range(8):
            y=188+31*slot;fill(c,x,y,36,28,PALE)
            if slot in advanced:fill(c,x,y,36,13,TEAL)
            if slot in committed:fill(c,x,y+15,36,13,BLUE)
    for slot in range(8):c.text(92,193+31*slot,f"槽 {slot}"+('' if slot in active else '（空闲）'),12,GRAY)
    c.text(450,467,'首轮清除起音准备标志；后续访问才推进包络并提交目标。',14,BLUE)
    c.text(450,505,'推进游标在池末截断本批；轮询游标还受实际更新数量影响。',13,GRAY)
    c.text(450,530,'横轴为受控调用周期；未换算为音频采样数或实际时间。',12,GRAY)
    c.save('voice-refresh-cadence')

    c=Canvas(940,550);c.text(470,12,'变化来源决定 TG 的平滑档位',24)
    c.text(470,52,'原 25 项整数系数表；音量、音高与滤波分别选择索引 D',13,GRAY)
    xy=axis(c,85,155,355,245,[(0,'0'),(1,'1'),(8,'8'),(16,'16'),(24,'24')],
            [(100,'100'),(1000,'1000'),(10000,'10000'),(65535,'65535')],lambda v:v/24,lambda v:(math.log10(v)-math.log10(80))/(math.log10(65535)-math.log10(80)))
    curve(c,[xy(i,v) for i,v in enumerate(d['coefficient_table'])],BLUE)
    c.text(260,116,'系数 K[D]（对数坐标）',14,BLUE);c.text(260,445,'D = min(所选标记, 24)',13,GRAY)
    c.box(500,95,410,94,'音量',['LFO 变化位 0x08：D = 1','其他情况：D = 24'],TEAL)
    c.box(500,212,410,94,'音高',['LFO 变化位 0x01：D = 0','否则 EG 位 0x10 取时间标记；其余取 24'],TEAL)
    c.box(500,329,410,94,'Filter A / B',['各自的 LFO 变化位：D = 1','否则各自的 EG 位取时间标记；其余取 24'],TEAL)
    c.text(470,483,'K[0] = 65535，K[1] = 2047，K[24] = 85；实际步长还取决于目标差值。',13,BLUE)
    c.text(470,520,'所有低七位标志组合、五种标记和三种差值方向另有直接提交检查。',12,GRAY)
    c.save('voice-refresh-smoothing')

    with (OUT/'voice-refresh-cadence.csv').open('w',newline='') as out:
        writer=csv.writer(out);writer.writerow(['program','oscillator','batch','cycle','elapsed','advance_cursor','poll_cursor','available','polled_slots','committed_slots','wait_requests'])
        for trace in d['traces']:
            for p in trace['steps']:writer.writerow([trace['program'],trace['oscillator'],trace['batch'],p['update'],p['elapsed'],p['cursor_advance'],p['cursor_poll'],p['available'],
                json.dumps(p['visits']),json.dumps([c['voice'] for c in p['commits']]),json.dumps(p['waits'])])
    with (OUT/'voice-refresh-commits.csv').open('w',newline='') as out:
        writer=csv.writer(out);writer.writerow(['program','oscillator','batch','cycle','voice','flags','amp_target','amp_previous','pitch_increment','amp_time','pitch_time','filter_A_time','filter_B_time','amp_command','pitch_step'])
        for trace in d['traces']:
            for p in trace['steps']:
                for item in p['commits']:writer.writerow([trace['program'],trace['oscillator'],trace['batch'],p['update'],item['voice'],item['flags'],item['amp'],item['amp_previous'],item['pitch'],
                    item['amp_time'],item['pitch_time'],*item['filter_times'],item['registers'].get('0x418',''),item['registers']['0x214']])
    print('Rendered two voice-refresh figures (PNG/SVG), with cadence and command CSV files.')
if __name__=='__main__':main()
