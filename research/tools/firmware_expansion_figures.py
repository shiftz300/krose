#!/usr/bin/env python3
"""Diagram expansion resource coverage and unresolved drum-kit dependencies."""
import collections,csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    d=json.loads((OUT/'expansion-pcm-check.json').read_text());assert d['passed'] and not d['smoke_only']
    c=Canvas(960,580);c.text(480,13,'扩展库已连接到原银行与区域寻址',24)
    c.text(480,54,'三套现有库共 76 个 Multisample；全部 128 键区域查询与独立表一致',13,GRAY)
    for panel,bank in enumerate(d['resources']['banks']):
        x=25+320*panel;logical=bank['logical_bank'];title={1:'OASYS Piano',2:'E.P. Collection',4:'Future Synth'}[bank['library']]
        c.box(x,111,270,112,title,[f"描述符银行 {2*logical} / {2*logical+1}",f"逻辑银行 {logical} → 测试槽 {bank['physical_slot']}",f"立体声目录：{len(bank['stereo_pairs'])} 对"],BLUE)
        c.arrow(x+135,223,x+135,268)
        c.box(x,268,270,112,f"{bank['multisamples']} 个 Multisample",[f"{bank['regions']} 条区域记录",f"{bank['samples']} 条原采样描述符",'键区上界、Sample 索引逐项核对'],TEAL)
    c.box(165,428,630,85,'新增 797 个单声道 PCM24 WAV',[
        'E.P. 602 个，Future Synth 195 个；帧数、采样率与每个导出字节通过检查',
        '三套银行的槽位置为私有测试装配；完整装载与音色发声继续连接'],GOLD)
    c.text(480,548,'WAV 保留源波形；循环、原起点、标志与区域根音继续保存在清单中。',12,GRAY)
    c.save('expansion-resource-banks')

    c=Canvas(960,600);c.text(480,13,'四套 Future Synth 鼓组的采样依赖',24)
    c.text(480,54,'按启用层统计；同一个键可含多层，立体声层仍按一个描述符计数',13,GRAY)
    c.text(160,116,'鼓组',15,BLUE);c.text(410,116,'板载银行 0 / 1',15,BLUE)
    c.text(625,116,'Future Synth 银行 10',15,TEAL);c.text(835,116,'未提供银行 12',15,GOLD)
    for index,kit in enumerate(d['expansion_drumkits']):
        counts=collections.Counter(s['bank'] for key in kit['keys'] for s in key['slots']);y=175+64*index
        c.text(160,y,kit['name'],16,BLUE);c.text(410,y,str(counts[0]+counts[1]),18,BLUE)
        c.text(625,y,str(counts[10]+counts[11]),18,TEAL);c.text(835,y,str(counts[12]),18,GOLD)
        c.line(45,y+40,915,y+40,'#edf3f6')
    missing=[(kit,key,slot) for kit in d['expansion_drumkits'] for key in kit['keys'] for slot in key['slots'] if not slot['available_bank']]
    reachable=sum(bool(slot['reachable_velocities']) for _,_,slot in missing)
    c.box(100,455,760,82,'45 条本库鼓采样目录已恢复，另有跨库缺口',[
        f"未提供银行涉及 {len(missing)} 条启用层，其中 {reachable} 条能被非零力度选中",
        '其余一条被原门槛遮住；这些引用单独保留，不纳入已具备资源的音色覆盖'],GOLD)
    c.text(480,570,'上述银行号为层描述符的编码值；银行 12 对应逻辑银行 6，当前资料没有该来源。',12,GRAY)
    c.save('expansion-drum-dependencies')

    with (OUT/'expansion-samples.csv').open('w',newline='') as out:
        fields=['library','id','file','frames','loop','flags','pitch','nominal_rate_exact','wav_rate_hz','relative_start','relative_end_inclusive','sha256'];writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
        for lib in d['exports']:
            for sample in lib['samples']:writer.writerow(dict(library=lib['library'],**{k:sample[k] for k in fields if k!='library'}))
    with (OUT/'expansion-region-map.csv').open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(d['resources']['maps'][0]));writer.writeheader();writer.writerows(d['resources']['maps'])
    with (OUT/'expansion-kit-dependencies.csv').open('w',newline='') as out:
        writer=csv.writer(out);writer.writerow(['kit','note','slot','bank','number','available_bank','reachable_velocity_count'])
        for kit in d['expansion_drumkits']:
            for key in kit['keys']:
                for slot in key['slots']:writer.writerow([kit['name'],key['note'],slot['slot'],slot['bank'],slot['number'],slot['available_bank'],len(slot['reachable_velocities'])])
    print('Rendered two expansion figures (PNG/SVG), with sample, region and dependency CSV files.')
if __name__=='__main__':main()
