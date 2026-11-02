#!/usr/bin/env python3
"""Actual section placement, retained duplicate links and capacity behavior."""
import csv,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD,PALE
from firmware_program_relocation import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def main():
    source=OUT/'resource-import-check.json';d=json.loads(source.read_text());assert d['passed'] and not d['smoke_only']
    kits=next(x for x in d['cases'] if x['tag']=='1KBD' and x['index']==4 and x['variant']=='original');assert kits['copied']==4
    c=Canvas(1180,860);c.text(590,15,'扩展鼓组：实际放置、共享引用与容量边界',24)
    c.text(590,56,'Future Synth；原版本 37 分节导入，目标起点 46。私有文件流与存储，无设备操作。',14,GRAY)
    for i,row in enumerate(kits['records']):
        c.box(30+290*i,104,250,110,f"用户槽 {42+row['index']}",[row['name'],f'文件中的第 {i+1} 套'],TEAL)
    c.text(590,250,'原 Program 导入后，再执行原引用修正',18,BLUE)
    columns=[170,530,700,980]
    for x,label in zip(columns,['Program / 名称','原鼓组号','新鼓组号','实际套件内容']):c.text(x,291,label,14,GRAY)
    selected=[x for x in d['links'] if x['destination_start']==46];assert len(selected)==4
    for i,row in enumerate(selected):
        y=333+48*i;c.line(40,y+33,1140,y+33,PALE)
        for x,value in zip(columns,[f"{row['program']:03d} / {row['name']}",str(row['stored_kit']),str(row['relocated_kit']),row['selected_kit_name']]):c.text(x,y,str(value),15,TEAL if x==980 else BLUE)
    c.text(590,553,'容量不足：仍消费并校验全部文件记录，只写入目标槽位能容纳的前缀',17,GOLD)
    for i,start in enumerate([54,55,56,57]):
        row=next(x for x in d['cases'] if x['tag']=='1KBD' and x['index']==start-42 and x['variant']=='original')
        c.box(30+290*i,605,250,102,f'目标起点 {start}',[f"写入 {row['copied']} / 4 套",f"分节函数返回 {row['returned']}"],GOLD)
    c.text(590,746,'校验错误或末记录读失败：函数返回 0 并恢复流位置，此前的目标写入保留。',14,GRAY)
    c.text(590,785,'插件应先校验分节及目标容量，再提交记录与引用；成功标志不能替代写入计数。',14,TEAL)
    c.text(590,824,'结论限于原分节与引用内核；外层安装器预检、错误恢复、旧格式和音频未在此执行。',13,GRAY)
    c.save('resource-import-placement')
    rows=[dict(library=x['library'],tag=x['tag'],bank=x['bank'],index=x['index'],last_bank=x['last_bank'],variant=x['variant'],returned=x['returned'],copied=x['copied'],stream_position=x['stream_position'],stream_length=x['stream_length']) for x in d['cases']]
    csvfile=OUT/'resource-import-cases.csv'
    with csvfile.open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    links=OUT/'resource-import-kit-links.csv'
    with links.open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(d['links'][0]));writer.writeheader();writer.writerows(d['links'])
    result=dict(passed=True,source_sha256=sha(source),tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/firmware_runtime_figures.py'),additional_helpers={'firmware_program_relocation.py':sha(ROOT/'research/tools/firmware_program_relocation.py')},csv_sha256=sha(csvfile),link_csv_sha256=sha(links),rows=len(rows),link_rows=len(d['links']),images=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in [ROOT/'research/docs/architecture/figures/resource-import-placement.png',ROOT/'research/docs/architecture/figures/resource-import-placement.svg']])
    (OUT/'resource-import-figure-check.json').write_text(json.dumps(result,indent=2)+'\n');print('Rendered resource placement and65/64-row evidence CSVs.')
if __name__=='__main__':main()
