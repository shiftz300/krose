#!/usr/bin/env python3
"""Plot CC121 state changes from a completed native live trace."""
import csv,hashlib,json,struct
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    source=OUT/'midi-reset-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    t=next(t for t in d['live'] if t['preset']==[0,0] and t['mode']==3 and t['sostenuto']==127 and t['source']==5)
    event=t['steps'][28]['event']['reset'];before=bytes.fromhex(event['channel_before']);after=bytes.fromhex(event['channel_after'])
    rows=[]
    for label,cc in [('CC7 音量缓冲',7),('CC10 声像缓冲',10),('CC11 表情',11),('CC64 延音',64),('CC66 选择延音',66)]:
        rows.append(dict(field=label,before=before[0x82+cc],after=after[0x82+cc],source=f'channel+{0x82+cc:02X}'))
    rows.extend([dict(field='弯音',before=struct.unpack_from('<h',before,0xFA)[0],after=struct.unpack_from('<h',after,0xFA)[0],source='channel+FA'),
        dict(field='RPN/NRPN 选择标志',before=before[0x114],after=after[0x114],source='channel+114')])
    for label,key in [('音量缓存','cached_volume'),('声像缓存','cached_pan'),('Part 微调（音分）','fine_tuning')]:
        rows.append(dict(field=label,before=event[key],after=event[key],source='native whole-record equality across reset'))
    assert [(r['before'],r['after']) for r in rows]==[(99,127),(100,64),(73,127),(127,0),(127,0),(32767,0),(143,0),(99,99),(100,100),(10,10)]
    c=Canvas(1000,660);c.text(500,12,'CC121 后的缓冲值与演奏缓存',24)
    c.text(500,52,'A000 / 模式 3 / 两踏板开启 / 来源 5；原函数更新 28 的状态',14,GRAY)
    for x,label in [(245,'状态字段'),(585,'重置前'),(800,'重置后')]:c.text(x,92,label,17,BLUE)
    for i,row in enumerate(rows):
        y=138+40*i;c.line(80,y+30,920,y+30,'#e5eef2')
        c.text(245,y,row['field'],16,BLUE if i<7 else TEAL);c.text(585,y,str(row['before']),17,GRAY)
        c.text(800,y,str(row['after']),17,GOLD if row['before']!=row['after'] else TEAL)
    c.text(500,570,'按住的四个声部继续保留；已松键的钢琴声部进入释音。',16,BLUE)
    c.text(500,608,'音量缓存仍为 99；表情恢复为 127，后续音量目标随之变化。',14,GRAY)
    c.save('midi-reset-state')
    dest=OUT/'midi-reset-state.csv'
    with dest.open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    check=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),csv_sha256=sha(dest),rows=len(rows),
        example=dict(preset=[0,0],mode=3,sostenuto=127,source=5,update=28),
        images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/midi-reset-state.png',ROOT/'research/docs/architecture/figures/midi-reset-state.svg']])
    (OUT/'midi-reset-state-figure-check.json').write_text(json.dumps(check,indent=2)+'\n');print('Rendered CC121 state PNG/SVG and 10-row CSV.')
if __name__=='__main__':main()
