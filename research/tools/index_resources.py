#!/usr/bin/env python3
"""Index existing artifacts without rewriting their historical metadata."""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[2]
RESEARCH=ROOT/'research'
DEST=RESEARCH/'derived/catalog'
WEB=ROOT.parent/'krose-website'

def read(path):return json.loads((ROOT/path).read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def size(path):return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink())

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    factory_path='research/derived/firmware/KROSS2_V124/sounds/factory/programs.json'
    expansions_path='research/derived/firmware/KROSS2_V124/sounds/programs.json'
    factory=read(factory_path);expansions=read(expansions_path)
    selection=read('research/output/Factory_Sound_Selection/rom-sound-catalog.json')
    starter=read('assets/factory-starter/manifest.json')
    native_ids={p['id'] for p in starter['programs']}
    web=read('../krose-website/public/catalog.json')
    kinds=Counter(p['kind'] for p in factory['programs'])
    groups=[
      ('原始资料','EXPCM001 原件','research/EXPCM001','未修改 KEP 与原始附带资料'),
      ('原始资料','设备备份与原始采集消息','research/libraries','USB 存储备份、TG 采集消息、官方扩展包原件'),
      ('原始资料','官方固件与手册下载','research/downloads','来源存档；不作为产品运行依赖'),
      ('原始资料','固件解包原件','research/firmware','与分析后的 ARM 镜像分开保存'),
      ('已解码采样','板载完整 WAV','research/output/Factory_ROM_WAV','4068 个音乐采样 + 2 个诊断样本；PCM24 容器'),
      ('已解码采样','Concert SE Grand WAV','research/output/Concert_SE_Grand_WAV','84 个立体声分区、3 个力度层；插件来源'),
      ('已解码采样','OASYS Piano 全部 WAV','research/output/OASYS_Piano_WAV','272 个单声道采样，10 个 multisample 条目；含导出/Opus清单'),
      ('研究试听','原机分类波形试听','research/output/Factory_Sound_Selection','489 个旋律波形试听、965 个单鼓试听；不是 1454 个完整预置'),
      ('研究试听','扩展包代表波形试听','research/output/Sound_Selection','E.P./Future Synth 的 8 个代表波形；不是整库导出'),
      ('产品输入','板载共享库','assets/factory-starter','357 个共享单声道采样、418 个区域、6 个 Program；首批数据驱动播放器'),
      ('产品输入','冻结插件资源','assets/concert-se-grand','5 个运行输入，当前仍为 Concert 专用采样/控制表'),
      ('测试输入','原 ARM 期望数据','tests/fixtures/concert-se-grand','5 个独立二进制回归输入，不链接到插件'),
      ('研究缓存','Opus 编码缓存','research/build/web-opus','原始 WAV 的有损派生物，供网页重新导出'),
      ('历史证据','迁移前源码与构建凭据','research/archive','旧记录保留；不代表本轮重建或新 ARM 验证'),
    ]
    entries=[]
    for category,name,path,note in groups:
        folder=ROOT/path
        entries.append(dict(category=category,name=name,path=path,bytes=size(folder),files=sum(p.is_file() for p in folder.rglob('*')),note=note))
    pointers={
      'TG_ROM':'research/derived/acquisitions/KROSS2_ROM_stage_b_20261031T215150691039Z/complete/TG-ROM-candidate.img',
      'firmware_ARM':'research/derived/firmware/KROSS2_V124/KROSSAPP.bin',
      'factory_Programs':factory_path,'expansion_Programs':expansions_path,
      'ROM_decode_evidence':'research/derived/firmware/KROSS2_V124/rom/decoding/original-arm-verification.json',
      'filter_ARM_evidence':'research/derived/verification/concert-filter-arm-comparison.json',
      'voice_ARM_evidence':'research/derived/verification/concert-voice-arm-comparison.json',
      'timing_ARM_evidence':'research/derived/verification/voice-timing-arm-comparison.json',
      'effects_ARM_evidence':'research/derived/verification/effects-catalog-arm-comparison.json',
      'web_AMS_ARM_evidence':'research/derived/verification/web-release-ams-arm.json',
    }
    fingerprint={k:dict(path=p,bytes=(ROOT/p).stat().st_size,sha256=sha(ROOT/p),read_only=not bool((ROOT/p).stat().st_mode & 0o222)) for k,p in pointers.items()}
    rows=[]
    for p in factory['programs']:
        melodic=p['kind']=='factory_A_F';source=p.get('program_file','');available=bool(source and (ROOT/source).is_file())
        rows.append(dict(id=p['bank_program'],name=p['name'],library='板载 A–F' if melodic else 'GM 名称目录',category=p['category'],raw_program=source,parameters='已提取' if available else '仅名称/分类，未恢复独立 Program 参数',samples='板载采样 ROM 已解码；未单独解析 GM 选样映射' if not melodic else '引用已恢复到完整 ROM',web='波形试听' if melodic else '未接入',native='首批 Program 引擎（部分行为近似）' if p['bank_program'] in native_ids else '未作为独立预置接入'))
    for p in expansions['programs']:
        source=p['path'];legacy=ROOT/source
        if not legacy.exists():legacy=RESEARCH/source
        assert legacy.is_file() and sha(legacy)==p['sha256'],source
        rows.append(dict(id=p['key'],name=p['name'],library=p['library'],category=str(p['category_raw']),raw_program=str(legacy.relative_to(ROOT)),parameters='已提取',samples='272 个扩展采样已导出，板载引用已补齐' if p['library_id']==1 else '容器已解密；整库 PCM 尚未批量导出',web='波形试听' if p['library_id']==1 else '仅 8 个跨包代表波形试听',native='Concert 专用实现' if p['key']=='EXPCM001:002' else '未作为独立预置接入'))
    with (DEST/'programs.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    raw=json.loads(subprocess.check_output([sys.executable,str(RESEARCH/'tools/verify_workspace.py')],cwd=ROOT,text=True))
    (DEST/'integrity.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
    report=dict(snapshot_date='2026-11-01',scope='Current filesystem/catalog inventory; historical ARM/DSP evidence is referenced, not re-executed.',
      factory_programs=kinds,expansion_programs=dict(Counter(p['library'] for p in expansions['programs'])),collections=entries,anchors=fingerprint,
      web=dict(path='../krose-website',commit=subprocess.check_output(['git','-C',str(WEB),'rev-parse','HEAD'],text=True).strip(),board_programs=768,oasys_programs=32,samples=len(web['samples']),audio_packs=len(web['packs']),full_original_Program_DSP=False),
      plugin=dict(scope='Accepted Concert route plus six shared-library factory Programs',runtime_files=7,test_fixture_files=5,all_factory_Programs_implemented=False),integrity=raw,
      historical_metadata_warning='Original programs.json fields ROM_PCM_available/sample_dependencies_complete are time-of-extraction snapshots. This index is a current overlay; original source files and hashes remain unchanged.')
    (DEST/'resources.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# 资源总索引','', '2026-11-01。本表由 `python3 research/tools/index_resources.py` 生成。旧报告不覆盖，当前状态以本索引和 [逆向进度](docs/PROGRESS.md) 为入口。','',
      '| 层级 | 资源 | 目录 | 文件数 | 大小 MiB | 用途 |','| --- | --- | --- | ---: | ---: | --- |']
    for e in entries:
        target='../'+e['path'] if e['path'].startswith(('assets/','tests/')) else e['path'].removeprefix('research/')
        lines.append(f"| {e['category']} | [{e['name']}]({target}) | `{e['path']}` | {e['files']} | {e['bytes']/1048576:.2f} | {e['note']} |")
    lines+=['','[完整机器清单](derived/catalog/resources.json) · [音色状态表 CSV](derived/catalog/programs.csv) · [本轮完整性检查](derived/catalog/integrity.json)','',
      '音色状态表含 768 条板载 A–F、265 条 GM 名称目录、128 条扩展包预置，共 1161 行。GM 行不代表已有参数或已完成该音色复刻。', '',
      '原始 `programs.json` 仍保留当时的 `ROM_PCM_available=false` 或扩展依赖不全标记；现已取得 ROM。本索引提供当前状态覆盖，不改写旧证据的字节。','',
      '原生播放器现有 Concert 兼容路径及 6 个板载首批 Program，见 [原生结构](../docs/NATIVE_ARCHITECTURE.md)。这些首批音色采用原参数驱动，但完整 FX/调制仍未重建。\n\n32 个 OASYS 预置是不同的参数和波形引用，不是 32 套互不重复的录音。网页单波形试听、完整 Program 复刻和桌面插件预置接入是不同阶段。','',
      '只读 ROM SHA-256：`'+fingerprint['TG_ROM']['sha256']+'`。镜像覆盖已恢复的音乐采样目录，不是整机所有 Flash/扩展存储的备份。','']
    (RESEARCH/'RESOURCES.md').write_text('\n'.join(lines))
    print(json.dumps(dict(collections=len(entries),program_rows=len(rows),integrity=raw),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
