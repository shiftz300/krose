#!/usr/bin/env python3
"""Render expansion startup evidence and raw kit references."""
import csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    d=json.loads((OUT/'expansion-voices-check.json').read_text());assert d['passed'] and not d['smoke_only']
    r=next(r for r in d['melodic'] if (r['program'],r['oscillator'],r['note'],r['velocity'])==('EXPCM001:000',1,63,1))
    a,b=r['voices'];assert a['amp_target']==b['amp_target']==613
    c=Canvas(960,600);c.text(480,14,'扩展音色已接到真实采样声部',24)
    c.text(480,54,'KROSS SE Grand · OSC 1 · MIDI 音符 63 · 力度 1',14,GRAY)
    c.box(315,103,330,94,'原 Program → 立体声层',['逻辑银行 2，Multisample 0 / 1','交叉权重 32768；层电平 117'],BLUE)
    for x,v in [(45,a),(525,b)]:
        c.arrow(480,197,x+195,248)
        c.box(x,248,390,100,f"区域 {v['region']} → Sample {v['sample']}",[
            f"根音 {v['root']} / 256；调音 {v['tune']}；区域电平 {v['region_correction']}",
            f"源 WAV：{v['source_wav'].split('/')[-1]}"],TEAL)
        c.arrow(x+195,348,x+195,395)
        c.box(x,395,390,100,f"原声部槽 {v['voice_slot']}",[
            f"共享音量目标 {v['amp_target']}；音高步进 {v['pitch_increment']}",
            '原采样模式、起止与循环控制字逐项比较'],BLUE)
    c.text(480,530,'两侧控制状态复制后均进入采样启动；副侧 gain 中间字段为 0，不能据此推断静音。',13,GRAY)
    c.text(480,563,'采样地址仍相对原 PCM 数据区；本图检查启动控制，完整音色音频尚待验证。',13,GOLD)
    c.save('expansion-voice-startup')

    c=Canvas(960,580);c.text(480,14,'四个扩展鼓组 Program 的原始引用',24)
    c.text(480,55,'私有检查按文件顺序放入用户槽 42–45；引用平移已确认，完整套件放置仍待核对',13,GRAY)
    c.text(285,110,'原 Program / 保存的套件号',15,BLUE);c.text(730,110,'私有槽中的套件',15,TEAL)
    for i,link in enumerate(d['kit_links']):
        y=156+77*i
        c.box(35,y,475,60,f"{link['program']}  {link['name']}",[f"保存编号 {link['stored_kit']}"],BLUE)
        c.arrow(510,y+30,590,y+30)
        c.box(590,y,335,60,link['fixture_kit_name'],[f"用户槽 {link['stored_kit']}"],TEAL)
    c.box(100,480,760,68,'按原编号检查，保留资源缺口',[
        '两个 Program 保存编号 45；11 组启动因逻辑银行 6 缺失而暂缓，均来自 043'],GOLD)
    c.save('expansion-voice-kit-links')

    with (OUT/'expansion-voice-startups.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['program','name','oscillator','note','velocity','deferred_missing_bank','voices','tg_starts'])
        for r in d['melodic']+d['drums']:w.writerow([r['program'],r['name'],r.get('oscillator',''),r['note'],r['velocity'],r['deferred_missing_bank'],len(r['voices']),r['tg_start_calls']])
    with (OUT/'expansion-voice-kit-links.csv').open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(d['kit_links'][0]));w.writeheader();w.writerows(d['kit_links'])
    print('Rendered expansion startup and kit-link figures, with two CSV files.')
if __name__=='__main__':main()
