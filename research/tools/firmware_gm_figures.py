#!/usr/bin/env python3
"""Illustrate verified GM bank fallback and low-key drum remapping."""
import csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    d=json.loads((OUT/'gm-programs-check.json').read_text());assert d['passed'] and not d['smoke_only']
    c=Canvas(950,550);c.text(475,13,'十一组逻辑 GM 银行，共用三份参数文件',24)
    c.text(475,53,'128 个基本音色 + 128 个实际变体 + 9 个鼓组；缺少的变体回退到基本音色',13,GRAY)
    entries=[(25,'G：基本音色','PROGGC.BIN',['逻辑银行 10 → 实体银行 10','程序号直接作为文件内索引','共 128 条，索引 0–127']),
             (345,'g1–g9：变体','PROGGV.BIN',['逻辑银行 11–19 → 实体银行 11','用每个基本音色的起点与数量查表','合计 128 条，数量最高为 9']),
             (665,'gd：鼓组','PROGGD.BIN',['逻辑银行 20 → 实体银行 12','程序号按范围映射到九套鼓组','64–127 回到 STANDARD'])]
    for x,title,file,lines in entries:c.box(x,111,260,138,title,[file,*lines],BLUE)
    c.box(85,325,780,120,'例：请求钢琴的第三个变体 g3-001',[
        'GM Acoustic Piano 只有两个变体，第三个请求缺少对应记录',
        '原映射改为 G001 → PROGGC.BIN 第 0 条；原返回值为 0',
        '插件应继续使用回退音色，避免把该返回值直接当作停止发声'],GOLD)
    c.text(475,489,'变体银行的 1152 种程序号组合中，128 种有记录，1024 种进入基本音色回退。',13,GRAY)
    c.save('gm-bank-fallback')

    normal=next(x for x in d['drums'] if x['id']=='gd-001' and not x['special'] and x['note']==24 and x['velocity']==64)
    special=next(x for x in d['drums'] if x['id']=='gd-001' and x['special'] and x['note']==24 and x['velocity']==64)
    c=Canvas(950,550);c.text(475,13,'GM 鼓组还会重排低音区按键',24)
    c.text(475,53,'全局模式值为 1 且 Part 银行为 20 时，在普通鼓组映射后再查 35 项表',13,GRAY)
    c.box(25,111,260,115,'按键输入 24',[
        'STANDARD 的编码鼓组号为 154','原存储入口转换为聚合索引 58','跨提供者取得 GM 鼓组'],BLUE)
    c.box(345,111,260,115,'普通鼓组映射',[
        '输入键已分配，映射距离为零','关闭 GM 特殊模式：使用键 24','开启特殊模式：查低音区表'],GOLD)
    c.box(665,111,260,115,'GM 表：24 → 75',[
        f"实际层取自键 {special['voices'][0]['key']}",
        f"Sample {special['voices'][0]['sample']}",'跟踪音符仍保留输入键 24'],TEAL)
    c.arrow(285,168,345,168);c.arrow(605,168,665,168)
    c.box(85,304,350,126,'关闭特殊模式',[
        f"按键记录 {normal['voices'][0]['key']}",f"Sample {normal['voices'][0]['sample']}",
        '同一输入会走到另一条真实采样链'],BLUE)
    c.box(515,304,350,126,'特殊表中的其他规则',[
        '13 → 86，23 / 24 → 75','25–28 → −1：抑制起音',
        '保留普通映射距离用于原音高计算'],TEAL)
    c.text(475,479,'九套 GM 鼓组的两种模式均遍历全部 128 键、127 个非零力度。',13,GRAY)
    c.text(475,515,'真实启动与 TG 采样命令已核对；完整 MIDI 入口与实际音频仍有缺口。',12,GRAY)
    c.save('gm-drum-low-keys')

    with (OUT/'gm-programs.csv').open('w',newline='') as out:
        fields=['id','name','logical_bank','program_number','source_path','source_offset','source_sha256','mode','official_id','official_mode']
        writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
        for row in d['records']:
            item={key:row[key] for key in fields if key in row};item.update(source_path=f"research/derived/acquisitions/KROSS2_local_20261101-022845/files/{row['source']}",source_offset=64+2140*row['index']);writer.writerow(item)
    with (OUT/'gm-bank-mapping.csv').open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(d['mapping'][0]));writer.writeheader();writer.writerows(d['mapping'])
    with (OUT/'gm-sample-chain.csv').open('w',newline='') as out:
        writer=csv.writer(out);writer.writerow(['group','id','oscillator','special','note','velocity','layer','side','sample','region_or_kit_key','weight'])
        for group in ['melodic','drums']:
            for row in d[group]:
                for v in row['voices']:writer.writerow([group,row['id'],row.get('oscillator',1),row.get('special'),row['note'],row['velocity'],v['layer'],v['side'],v['sample'],v.get('region',v.get('key')),v['weight']])
    print('Rendered two GM figures (PNG/SVG), with record, mapping and sample CSV files.')
if __name__=='__main__':main()
