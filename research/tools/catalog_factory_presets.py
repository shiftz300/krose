#!/usr/bin/env python3
"""Catalog the original KROSS2 factory Programs and trace bank-file selection.

Factory names come from the official standard-model Voice Name List. Pure ARM
lookup excerpts establish bank file names; no factory Program bytes or ROM PCM
are invented when the update archive does not contain them.
"""
from layout import PRODUCT_ROOT
import argparse
import collections
import contextlib
import csv
import hashlib
import json
import re
import struct
import zipfile

from program_firmware import ROOT, Firmware, Arm, FW_SHA, BASE
from firmware_inspect import inspect
from analyze_concert_program import GROUP_NAMES, LABELS

PDF=ROOT/'research/downloads/KROSS2_Voice_Name_List_20180323.pdf'
DERIVED=ROOT/'research/derived/firmware/KROSS2_V124/sounds/factory'
OUTPUT=ROOT/'output/Factory_Sound_Selection'
PRELOAD=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def preload_parameters(firmware,programs,arm):
    raw=PRELOAD.read_bytes()
    assert digest(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    assert raw[:4]==b'tra ' and struct.unpack_from('>I',raw,4)[0]==len(raw)-8 and raw[16:20]==b'KRS2'
    start=0x1EF220;stride=2140
    reference=(ROOT/'output/kep-analysis/Concert_SE_Grand/program.bin').read_bytes();schema=[]
    for ns in range(0x27,0x60):schema.extend(firmware.group(ns,reference))
    # The editor records end at the end of the second 380-byte OSC block.
    # Four KEP alignment bytes are not present; no numeric field needs them.
    spans=[f['program_offset']+(1,2,4,1,2,4)[f['descriptor']['type']] for f in schema]
    assert max(spans)<=stride
    effects=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/catalog/effects.json').read_text())['effects']
    all_values={};comparisons=0;effect_comparisons=0;source_dir=ROOT/'research/derived/factory/KROSS2_Editor_100/programs'
    for item in programs:
        if item['kind']!='factory_A_F':continue
        bank=item['bank_program'];index=(ord(bank[0])-65)*128+int(bank[1:]);offset=start+index*stride
        data=raw[offset:offset+stride];original_name=data[:24].decode('ascii').rstrip(' \0')
        assert ' '.join(original_name.split())==item['name'],(bank,original_name,item['name'])
        assert data[0x508]&7=={'S':0,'D':1,'d':2}[item['oscillator_mode']]
        path=source_dir/f'{bank}_{re.sub("[^A-Za-z0-9_.-]+","_",original_name).strip("_")}.bin'
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():assert path.read_bytes()==data
        else:path.write_bytes(data)
        values=[];by_id={}
        for f in schema:
            off=f['program_offset'];value=firmware.read_value(data,off,f['descriptor'])
            if arm:assert arm.parameter(data[off:],f['descriptor'])==value;comparisons+=1
            values.append(value);by_id[(f['namespace'],f['index'])]=value
        all_values[bank]=values
        oscillators=[]
        for osc in range(2):
            base=0x564+380*osc;slots=[]
            for slot in range(4):
                o=base+8*slot
                if not data[o]&1:continue
                slots.append(dict(slot=slot+1,bank=data[o+1],number=struct.unpack_from('<H',data,o+2)[0]&4095,level=data[o+4],
                                  bottom_velocity=data[base+32+slot*4] if slot<3 else 1,
                                  crossfade_width=data[base+33+slot*4] if slot<3 else 0))
            groups={}
            for ns,name in GROUP_NAMES.items():
                selected=[f for f in schema if f['namespace']==ns+osc*16]
                groups[name]={LABELS.get(ns,{}).get(f['index'],f'field_{f["index"]}'):by_id[(ns+osc*16,f['index'])] for f in selected}
            oscillators.append(dict(oscillator=osc+1,active=(item['oscillator_mode']=='D' or osc==0),slots=slots,groups=groups))
        fx=[]
        for i in range(7):
            payload=0x18+76*i if i<5 else (0x194,0x1d8)[i-5];head=payload+64;eid=data[head];assert eid<len(effects)
            parameters=[]
            for parameter in effects[eid]['parameters']:
                off=payload+parameter['payload_offset'];desc=parameter['descriptor']
                value=firmware.read_value(data,off,desc)
                if arm:assert arm.parameter(data[off:],desc)==value;effect_comparisons+=1
                parameters.append(dict(index=parameter['index'],label=parameter['label'],value=value,program_offset=off))
            entry=dict(slot=f'IFX{i+1}' if i<5 else f'MFX{i-4}',id=eid,name=effects[eid]['name'],
                       enabled=bool(data[head+1]&64),parameters=parameters)
            if i<5:entry.update(chain_enabled=bool(data[head+1]&128),chain_to_ifx=data[head+2],output_bus_raw=data[head+5]&7,
                                pan_raw=data[head+4],send1=data[head+6],send2=data[head+7])
            fx.append(entry)
        item.update(program_parameters_available=True,program_source_offset=offset,program_record_bytes=stride,
                    program_file=str(path.relative_to(PRODUCT_ROOT)),program_sha256=hashlib.sha256(data).hexdigest(),
                    source_original_name=original_name,oscillators=oscillators,effects=fx,
                    status='Original factory Program parameters recovered from official editor PRELOAD; ROM PCM still unavailable')
        if index%128==127:print('Recovered factory bank',bank[0],flush=True)
    # The following four user banks are initialized Programs in this reference.
    assert all(raw[start+i*stride:start+i*stride+8]==b'InitProg' for i in range(768,1280))
    save(DERIVED/'parameter-schema.json',dict(firmware_sha256=FW_SHA,fields=schema))
    save(DERIVED/'parameter-values.json',dict(fields_per_program=len(schema),values=all_values))
    return dict(path=str(PRELOAD.relative_to(PRODUCT_ROOT)),sha256=digest(PRELOAD),bytes=len(raw),
                header_length_pass=True,model_tag='KRS2',program_table_offset=start,record_bytes=stride,
                factory_records=768,following_initialized_user_records=512,fields_per_program=len(schema),
                maximum_parameter_span=max(spans),ARM_parameter_getter_comparisons=comparisons,
                ARM_effect_parameter_comparisons=effect_comparisons,
                record_layout='2140-byte editor Program, all indexed parameter offsets fit unchanged; reference KEP stride2144 has four trailing zero bytes',
                ROM_PCM_present=False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args()
    import pdfplumber
    firmware=Firmware();programs=[];category=None
    with pdfplumber.open(PDF) as pdf:
        assert len(pdf.pages)==96
        for page_index in range(2,14):
            page=pdf.pages[page_index];text=page.extract_text()
            found=re.search(r'Category: ([A-Z./ ]+)',text)
            if found:category=found.group(1).strip()
            assert category
            for table in page.extract_tables():
                for row in table[1:]:
                    assert len(row)==5,row
                    index,bank,name,subcategory,mode=[' '.join((v or '').split()) for v in row]
                    assert re.fullmatch(r'\d{3}',index) and re.fullmatch(r'[A-FG]\d{3}|g[1-9d]-\d{3}',bank),(page_index,row)
                    assert name and subcategory and mode in ('S','D','d'),row
                    factory=bool(re.fullmatch(r'[A-F]\d{3}',bank))
                    bank_file=f'PPROGI{bank[0]}.BIN' if factory else None
                    programs.append(dict(bank_program=bank,name=name,category=category,category_index=int(index),
                                         subcategory=subcategory,oscillator_mode=mode,source_pdf_page=page_index+1,
                                         kind='factory_A_F' if factory else 'GM',factory_bank_file=bank_file,
                                         program_parameters_available=False,ROM_PCM_available=False,plugin_implemented=False,
                                         status='Named factory Program from official list; actual bank record/ROM audio unavailable in current update'))
    factory=[p for p in programs if p['kind']=='factory_A_F']
    assert len(factory)==768 and len(factory)==len({p['bank_program'] for p in factory})
    duplicate_ids={key:[dict(category=p['category'],name=p['name'],page=p['source_pdf_page']) for p in programs if p['bank_program']==key]
                   for key,count in collections.Counter(p['bank_program'] for p in programs).items() if count>1}
    # Preserve the official GM table's G016 conflict; do not silently change a
    # printed bank number using a different model's list or a guessed correction.
    assert set(duplicate_ids)=={'G016'}
    for bank in 'ABCDEF':assert {p['bank_program'] for p in factory if p['bank_program'][0]==bank}=={f'{bank}{i:03d}' for i in range(128)}
    for cat in {p['category'] for p in programs}:
        indices=[p['category_index'] for p in programs if p['category']==cat]
        assert sorted(indices)==list(range(len(indices))),cat

    table=0x457BB8;bank_files=[];arm=Arm(firmware) if args.verify_arm else None
    for index,bank in enumerate('ABCDEF',7):
        offset=firmware.pointer(table+index*4);name=firmware.string(offset);assert name==f'PPROGI{bank}.BIN'
        captures=[]
        if arm:
            # Run original selectors, stopping before any constructor/file I/O.
            frame=0x11090000
            arm.write(frame-0x11C,index);arm.set('FP',frame)
            arm.uc.emu_start(BASE+0x2C5720,BASE+0x2C572C,count=10)
            assert arm.get('R3')==BASE+offset
            captures.append(dict(entry='0x2c5720',stop='0x2c572c',filename_pointer=hex(arm.get('R3'))))
            arm.write(frame-0x1208,index);arm.set('FP',frame)
            arm.uc.emu_start(BASE+0x17F610,BASE+0x17F620,count=10)
            assert arm.get('R1')==BASE+offset
            captures.append(dict(entry='0x17f610',stop='0x17f620',filename_pointer=hex(arm.get('R1'))))
        bank_files.append(dict(bank=bank,filename=name,string_offset=offset,filename_table_index=index,
                               factory_Programs_in_official_list=128,ARM_selector_captures=captures))
    preload=preload_parameters(firmware,programs,arm)
    rom_pointer=firmware.u32(0x20CF3C);rom_count=firmware.u32(0x20CF48)
    assert rom_pointer==BASE+0x48F5CC and rom_count==497
    if arm:assert (arm.call(0x20CF34)&0xffffffff)==rom_pointer and arm.call(0x20CF40)==rom_count
    rom=[]
    for i in range(rom_count):
        offset=rom_pointer-BASE+i*28;first,count,flags=struct.unpack_from('<HBB',firmware.data,offset)
        name=firmware.data[offset+4:offset+28].decode('ascii').rstrip(' \0')
        rom.append(dict(index=i,name=name,offset=offset,first_region=first,region_count=count,flags=flags,
                        role='diagnostic tone' if name=='Sine 1kHz' else 'ROM waveform metadata',PCM_available=False))
    stereo_pairs=[]
    for i in range(len(rom)-1):
        left,right=rom[i]['name'],rom[i+1]['name']
        if left.endswith('-L') and right.endswith('-R') and left[:-2].rstrip()==right[:-2].rstrip():stereo_pairs.append([i,i+1])
    for program in factory:
        for osc in program['oscillators']:
            for slot in osc['slots']:
                if program['oscillator_mode']=='d':
                    slot['source_scope']='Drum-mode fields retained; multisample interpretation not applied'
                    continue
                bank,number=slot['bank'],slot['number']
                indices=[number] if bank==0 else stereo_pairs[number] if bank==1 and number<len(stereo_pairs) else []
                assert indices and all(i<len(rom) for i in indices),(program['bank_program'],slot)
                slot['ROM_multisample_indices']=indices
                slot['ROM_multisample_names']=[rom[i]['name'] for i in indices]
                slot['source_scope']='Mono index or ordered matching L/R pair inferred from ROM metadata; full allocator not executed'
    archive=ROOT/'research/downloads/KROSS2_V124.zip'
    with zipfile.ZipFile(archive) as z:members=[m.filename for m in z.infolist() if not m.is_dir()]
    present={name.split('/')[-1] for name in members}
    assert all(b['filename'] not in present for b in bank_files)
    category_counts=dict(sorted(collections.Counter(p['category'] for p in factory).items()))
    result=dict(firmware_sha256=FW_SHA,source_pdf=str(PDF.relative_to(PRODUCT_ROOT)),source_pdf_sha256=digest(PDF),
                model_scope='Standard KROSS2 original factory list, official revision2018-03-23; SE/88MB extra sound banks excluded',
                program_count=len(programs),factory_A_F_count=len(factory),GM_count=len(programs)-len(factory),
                source_table_duplicate_bank_ids=duplicate_ids,
                category_counts=category_counts,programs=programs,bank_files=bank_files,
                recovered_preload=preload,
                update_archive=dict(path=str(archive.relative_to(PRODUCT_ROOT)),sha256=digest(archive),members=members,
                                    factory_bank_files_present=False),
                factory_bank_IO=dict(filename_table='0x457bb8',media_path='A:/',
                                     inspected_entries=['0x2c5684','0x2c5aa0','0x2c5bcc','0x2c5f18','0x17f610'],
                                     scope='Static filename/file-transfer path tracing, plus pure original ARM selectors; no filesystem/device OS executed'),
                ROM_multisample_table=dict(offset=rom_pointer-BASE,count=rom_count,record_bytes=28,records=rom,
                                           scope='Metadata, not factory Program records or decoded PCM'),
                missing_data=['Factory ROM PCM payloads; official PRELOAD supplies Program parameters, not those samples'],
                acceptance='User accepts current Concert approximation and waives physical A/B; focus is original machine factory Programs, not EXPCM expansion libraries')
    DERIVED.mkdir(parents=True,exist_ok=True);OUTPUT.mkdir(parents=True,exist_ok=True)
    save(DERIVED/'programs.json',result)
    fields=['bank_program','name','category','category_index','subcategory','oscillator_mode','factory_bank_file','source_pdf_page']
    for path in (DERIVED/'programs.csv',OUTPUT/'factory-programs.csv'):
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(factory)
    with (DERIVED/'GM-programs.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(p for p in programs if p['kind']=='GM')
    with (DERIVED/'factory-load.arm.txt').open('w') as stream,contextlib.redirect_stdout(stream):
        for start,end in ((0x2C5700,0x2C5778),(0x2C5AA0,0x2C5BC0),(0x2C5CE4,0x2C5D20),(0x17F610,0x17F648),(0x20CF34,0x20CF4C)):
            inspect(firmware.data,start,end)
    titles={'PIANO':'钢琴','E.PIANO':'电钢琴','ORGAN':'风琴','BELL':'钟／槌击','STRINGS':'弦乐／人声','BRASS':'铜管／木管','SYNTH LEAD':'合成器主音','SYNTH PAD':'铺底','GUITAR':'吉他','BASS':'贝斯','DRUM/SFX':'鼓组／音效'}
    recommended=['A000','A016','A034','A064','A075','B019','C001','D010','D103','E054','E098']
    by_bank={p['bank_program']:p for p in factory}
    text='# KROSS2 原机出厂预置音色选择\n\n用户已认可当前 Concert 的听感，不要求真琴 A/B。这里列的是普通 KROSS2 原机 A-F 出厂 Program，排除 EXPCM 扩展包和插件自定义 Warm/Wide。依据官方 2018-03-23 音色表；SE/88MB 额外预置另算。\n\n'
    text+='已从官方编辑器随附 `PRELOAD.KRS2all` 真正拆出 **768 个 A-F 原机预置的参数**，每银行 128 个，并与官方目录的名称/OSC 模式逐项核对。所有字段再对照固件原 ARM getter。另有 GM 名录单列。**原机 ROM PCM 尚未取得，这些新预置尚未接入播放器，不能宣称已经复刻。**\n\n'
    text+='## 先从这些原机音色挑\n\n| 编号 | 原机名称 | 类别 |\n| --- | --- | --- |\n'
    for key in recommended:
        p=by_bank[key];text+=f'| {key} | {p["name"]} | {titles[p["category"]]} |\n'
    text+='\n可直接告诉我银行编号和名称，例如 `A034 M1 Piano`。名称和类别不作为听感测量；选定后研究相应原 Program。\n\n## 当前可用的数据与缺项\n\n'
    text+='- 固件里已定位六个原机预置银行文件名和读取/传输代码，12 次原 ARM 选择器执行均与表一致。\n- 当前 v1.2.4 更新 ZIP 没有这些银行文件；本轮从官方编辑器归档找到 PRELOAD 数据，未运行安装程序。\n- 每个原机 Program 为 2140 字节，已保存原始切片，导出双 OSC、力度槽、滤波/包络/AMS 和效果配置。\n- 固件另有 497 条 ROM 波形元数据（含诊断正弦波）；这里保留为采样索引，不等于取得 PCM。\n- 所有原机预置仍待选定后制作。当前插件依然只实现 Concert 及本项目 Warm/Wide 变体。\n- 本轮没有修改播放器、复制或安装 VST3。\n\n完整 CSV： [factory-programs.csv](factory-programs.csv)。逆向证据：[FACTORY_SOUNDS.md](../../docs/FACTORY_SOUNDS.md)。\n\n'
    for category in titles:
        selected=[p for p in factory if p['category']==category]
        text+=f'## {titles[category]} / {category}（{len(selected)}）\n\n| 银行编号 | 原机名称 | 子类别 | OSC |\n| --- | --- | --- | --- |\n'
        for p in selected:text+=f'| {p["bank_program"]} | {p["name"]} | {p["subcategory"]} | {p["oscillator_mode"]} |\n'
        text+='\n'
    (OUTPUT/'README.md').write_text(text)
    report=dict(firmware_sha256=FW_SHA,source_pdf_sha256=digest(PDF),factory_A_F_count=len(factory),GM_count=result['GM_count'],
                category_counts=category_counts,bank_coverage='Each A-F has exactly000..127 once; category indices continuous; original GM G016 conflict retained separately',
                ARM_bank_selector_cases=12 if arm else 0,ARM_ROM_pointer_and_count_getters=2 if arm else 0,
                factory_bank_files_present_in_update=False,raw_Program_parameters_extracted=True,ROM_PCM_extracted=False,
                recovered_preload=preload,
                output_sha256={str(p.relative_to(PRODUCT_ROOT)):digest(p) for p in (DERIVED/'programs.json',DERIVED/'programs.csv',DERIVED/'parameter-schema.json',DERIVED/'parameter-values.json',OUTPUT/'README.md',OUTPUT/'factory-programs.csv')},
                tool_sha256={name:digest(ROOT/'tools'/name) for name in ('catalog_factory_presets.py','program_firmware.py','analyze_concert_program.py')},
                scope='Original factory Program bytes from official editor PRELOAD, numeric fields/effect parameters checked against ARM; no factory ROM audio decode claim')
    save(ROOT/'research/derived/verification/factory-sound-catalog-check.json',report)
    print('PASS',len(factory),'original A-F Programs,',result['GM_count'],'GM entries, 12 original ARM bank selectors and 2 ROM getters' if arm else 'metadata only')
    print('Category counts:',category_counts)


if __name__=='__main__':main()
