#!/usr/bin/env python3
"""Plot native-checked MIDI tuning, bend and bank translation behavior."""
import csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_midi_parameters import bend_value
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    d=json.loads((OUT/'midi-parameters-check.json').read_text());banks=json.loads((OUT/'midi-banks-check.json').read_text());assert d['passed'] and banks['passed']
    c=Canvas(960,540);c.text(480,14,'MIDI 微调与弯音的原整数映射',24)
    c.text(480,55,'微调显示旋律模式的绝对值；鼓模式还需保留合并调音字段的百位与余数',13,GRAY)
    for panel,title,low,high,fn in [(0,'RPN 1：Fine Tuning',-100,100,lambda v:((v-8192)*25)>>11),(1,'Pitch Bend',-32768,32768,lambda v:bend_value(v&127,v>>7))]:
        x=72+480*panel;y=125;w=340;h=230;c.text(x+w/2,90,title,18,BLUE)
        for v in [low,0,high]:
            yy=y+h-(v-low)*h/(high-low);c.line(x,yy,x+w,yy,'#e5eef2');c.text(x-30,yy-7,str(v),11,GRAY)
        c.line(x,y,x,y+h);c.line(x,y+h,x+w,y+h)
        for v in [0,8192,16383]:c.text(x+v/16383*w,y+h+12,str(v),11,GRAY)
        points=[(x+v/16383*w,y+h-(fn(v)-low)*h/(high-low)) for v in list(range(0,16384,32))+[16383]]
        for a,b in zip(points,points[1:]):c.line(*a,*b,TEAL,2)
        c.text(x+w/2,398,'14 位输入值',12,GRAY)
    c.box(80,445,800,65,'弯音补低两位：((v << 2) | ((v >> 7) & 3)) - 32768',[
        '中心 8192 → 0；最大 16383 → 32767；直接左移的最大值只有 32764'],GOLD)
    c.save('midi-tuning-bend')
    c=Canvas(960,540);c.text(480,14,'同一银行消息随映射模式改变含义',24)
    c.text(480,55,'输入表示 MSB:LSB；表中值来自原银行转换函数，完整音色装载仍需连接',13,GRAY)
    c.text(150,111,'输入 / 映射开关',15,BLUE);c.text(445,111,'内部银行 / Program',15,BLUE);c.text(770,111,'特殊低键鼓模式',15,BLUE)
    examples=banks['examples'][:-1]
    for i,row in enumerate(examples):
        y=157+45*i;msb,lsb=divmod(row['encoded_bank'],256)
        c.text(150,y,f"{msb}:{lsb} / {row['alternate']}",15,BLUE);c.text(445,y,f"{row['bank']} / {row['program']}",15,TEAL);c.text(770,y,str(row['special_low_drums']),15,GOLD)
        c.line(40,y+29,920,y+29,'#edf3f6')
    c.text(480,460,'两字节均缺失时返回失败；单字节缺失按零补齐。',14,GRAY)
    c.text(480,494,'部分直接银行编码绕过可用性查询；其余路径中，空银行可回退为 0 并保持成功返回。',13,GRAY)
    c.save('midi-bank-mapping')
    with (OUT/'midi-tuning-bend.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['input14','fine_melodic','pitch_bend','plain_shift_difference'])
        for v in range(16384):w.writerow([v,((v-8192)*25)>>11,bend_value(v&127,v>>7),(v>>7)&3])
    with (OUT/'midi-bank-examples.csv').open('w',newline='') as out:
        fields=list(banks['examples'][0]);w=csv.DictWriter(out,fieldnames=fields);w.writeheader();w.writerows(banks['examples'])
    print('Rendered MIDI tuning/bend and bank PNG/SVG figures, with two CSV files.')
if __name__=='__main__':main()
