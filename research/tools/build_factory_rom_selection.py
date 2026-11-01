#!/usr/bin/env python3
"""Build local dry-waveform auditions and a searchable factory sound picker.

Does not modify the player, plugin resources, firmware, or installed plugins.
Program rows link to their source multisamples, not a synthesized Program demo.
Requires numpy/scipy in the research Python environment.
"""
import argparse
import collections
import csv
import functools
import hashlib
import json
import math
import re
import struct
import wave
from fractions import Fraction

import numpy as np
from scipy.signal import resample_poly

from decode_factory_rom import CATALOG, DERIVED, OUTPUT, ROM_SHA, load, region_increment, save
from program_firmware import Firmware, ROOT

SELECTION = ROOT / 'output/Factory_Sound_Selection'
RATE = 48000
RECOMMENDED = ['A000', 'A016', 'A034', 'A064', 'A075', 'B019', 'C001', 'D010', 'D103', 'E054', 'E098']


def slug(value):
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', value).strip('_')


def csv_write(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)


def paired_groups(items):
    """Only adjacent, exact matching -L/-R names are grouped; IDs remain visible."""
    result = []; i = 0
    while i < len(items):
        a = items[i]
        if i + 1 < len(items) and a['name'].endswith('-L') and items[i+1]['name'] == a['name'][:-2] + '-R':
            result.append([a, items[i+1]]); i += 2
        else:
            result.append([a]); i += 1
    return result


class Auditioner:
    def __init__(self):
        self.fw = Firmware()
        self.samples = load('sample-descriptors')
        self.regions = load('key-regions')
        self.max_resample_error_cents = 0.0

    @functools.lru_cache(maxsize=128)
    def audio(self, sample_id):
        with wave.open(str(OUTPUT / f'samples/{sample_id:04d}.wav'), 'rb') as w:
            raw = w.readframes(w.getnframes())
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        values = b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16
        values = (values << 8) >> 8
        return values.astype(np.float64) / 8388608

    def resample(self, audio, increment, frames, loop=None):
        source_count = math.ceil(frames * increment / 8192) + 32
        indices = np.arange(source_count)
        if loop is not None:
            lo, hi = loop
            beyond = indices >= hi
            indices[beyond] = lo + (indices[beyond] - hi) % (hi - lo)
            source = audio[indices]
        else:
            source = np.zeros(source_count)
            length = min(source_count, len(audio)); source[:length] = audio[:length]
        ratio = Fraction(8192, increment).limit_denominator(512)
        error = abs(1200 * math.log2(float(ratio) / (8192 / increment)))
        self.max_resample_error_cents = max(self.max_resample_error_cents, error)
        result = resample_poly(source, ratio.numerator, ratio.denominator)
        if len(result) < frames:
            result = np.pad(result, (0, frames-len(result)))
        result = result[:frames].copy()
        # Generic audition fades, not the native Program envelope.
        attack = min(96, frames // 4); release = min(1920, frames // 4)
        result[:attack] *= np.linspace(0, 1, attack)
        result[-release:] *= np.linspace(1, 0, release)
        return result

    def note(self, ms, midi, duration):
        regions = self.regions[ms['first_region']:ms['first_region']+ms['region_count']]
        r = next((r for r in regions if r['top_key'] >= midi), regions[-1])
        sample_id = r['sample_index_raw']; descriptor = self.samples[sample_id]
        audio = self.audio(sample_id)
        increment = region_increment(self.fw, descriptor, r, midi)
        lo = descriptor['loop_start'] - descriptor['start']
        # Forward sustain is an audition convention. Raw mode flags and restart
        # words are retained in the raw manifest for later complete TG research.
        loop = (lo, len(audio)-1) if descriptor['flags'] & 0x10 and len(audio)-1-lo >= 8 else None
        return self.resample(audio, increment, round(duration*RATE), loop)

    def phrase(self, group):
        total = np.zeros((round(3.9*RATE), len(group)))
        for start, midi in [(0, 48), (.55, 55), (1.10, 60), (1.65, 67)]:
            for ch, ms in enumerate(group):
                audio = self.note(ms, midi, .62)
                offset = round(start*RATE); total[offset:offset+len(audio),ch] += audio
        for midi in (60, 64, 67):
            for ch, ms in enumerate(group):
                audio = self.note(ms, midi, 1.5) / 3
                offset = round(2.3*RATE); total[offset:offset+len(audio),ch] += audio
        return total

    def drum(self, group):
        channels = []
        for d in group:
            descriptor = self.samples[d['sample_index']]
            raw = self.audio(d['sample_index'])
            increment = self.fw.phase_increment(descriptor['pitch_field']*2)
            length = min(round(3*RATE), math.ceil(len(raw)*8192/increment)+1920)
            channels.append(self.resample(raw, increment, length))
        length = max(map(len, channels))
        return np.column_stack([np.pad(a, (0,length-len(a))) for a in channels])


def write_preview(path, audio):
    assert np.isfinite(audio).all() and len(audio) > 0
    peak = float(np.max(np.abs(audio)))
    # Preview-only loudness matching. Full sample WAVs remain unnormalized.
    gain = min(8.0, .80 / peak) if peak else 1.0
    audio = audio * gain
    assert np.max(np.abs(audio)) < .801
    data = np.rint(audio * 32767).astype('<i2')
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(data.shape[1]); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(data.tobytes())
    return dict(preview_frames=len(data), preview_seconds=len(data)/RATE,
                preview_channels=data.shape[1], preview_gain=gain,
                preview_peak=float(np.max(np.abs(audio))), preview_rms=float(np.sqrt(np.mean(audio*audio))),
                preview_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def build():
    SELECTION.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((OUTPUT / 'manifest.json').read_text())
    assert manifest['ROM_sha256'] == ROM_SHA and len(manifest['samples']) == 4070
    audition = Auditioner(); waves = []; drums = []; ms_to_wave = {}
    factory = json.loads((ROOT / 'research/derived/firmware/KROSS2_V124/sounds/factory/programs.json').read_text())['programs']
    programs = [p for p in factory if p['kind'] == 'factory_A_F']
    uses = collections.defaultdict(list)
    for p in programs:
        if p['oscillator_mode'] == 'd':
            continue
        for o in p['oscillators']:
            if o['active']:
                for s in o['slots']:
                    for ms in s.get('ROM_multisample_indices', []):
                        if p['bank_program'] not in uses[ms]: uses[ms].append(p['bank_program'])
    for group in paired_groups(load('multisamples')[:496]):
        first = group[0]; ids = [m['index'] for m in group]
        name = first['name'][:-2].rstrip() if len(group)==2 else first['name']
        key = f'MS{ids[0]:03d}'
        relative = f'waveform-previews/{key}_{slug(name)}.wav'
        stats = write_preview(SELECTION / relative, audition.phrase(group))
        sample_ids = sorted({r['sample_index_raw'] for m in group for r in audition.regions[m['first_region']:m['first_region']+m['region_count']]})
        used = sorted(set(p for ms in ids for p in uses[ms]))
        categories = sorted({p['category'] for p in programs if p['bank_program'] in used})
        item = dict(id=key, name=name, indices=ids, channels=len(group), region_count=first['region_count'],
                    category=' / '.join(categories) or '未被 A–F 直接使用', categories=categories,
                    preview=relative, sample_ids=sample_ids, used_by=used, **stats)
        waves.append(item)
        for i in ids: ms_to_wave[i] = item
        if len(waves)%100==0: print('Waveform auditions',len(waves),flush=True)
    for group in paired_groups(load('drumsamples')):
        first = group[0]; ids=[d['index'] for d in group]
        name = first['name'][:-2].rstrip() if len(group)==2 else first['name']
        key = f'DR{ids[0]:04d}'
        relative=f'drum-previews/{key}_{slug(name)}.wav'
        stats=write_preview(SELECTION/relative,audition.drum(group))
        drums.append(dict(id=key,name=name,indices=ids,channels=len(group),category='DRUM/SFX',
                          sample_ids=[d['sample_index'] for d in group],preview=relative,**stats))
        if len(drums)%200==0:print('Drum auditions',len(drums),flush=True)
    rows=[]
    for p in programs:
        waveform_ids=[];layers=[];unresolved=[]
        for osc in p['oscillators']:
            if not osc['active']:continue
            for slot in osc['slots']:
                layer=dict(oscillator=osc['oscillator'],slot=slot['slot'],bank=slot['bank'],number=slot['number'],
                           bottom_velocity=slot['bottom_velocity'],crossfade_width=slot['crossfade_width'],level=slot['level'])
                if p['oscillator_mode']=='d':
                    layer.update(kind='drumkit',drumkit_index=slot['number'])
                else:
                    source=slot.get('ROM_multisample_indices',[])
                    keys=list(dict.fromkeys(ms_to_wave[i]['id'] for i in source if i in ms_to_wave))
                    layer.update(kind='multisample',multisample_indices=source,waveform_ids=keys)
                    if not keys:unresolved.append(layer.copy())
                    waveform_ids.extend(keys)
                layers.append(layer)
        waveform_ids=list(dict.fromkeys(waveform_ids))
        rows.append(dict(id=p['bank_program'],name=p['name'],category=p['category'],subcategory=p['subcategory'],
                         oscillator_mode=p['oscillator_mode'],waveform_ids=waveform_ids,layers=layers,
                         effects=[f'{e["slot"]}: {e["name"]}' for e in p['effects'] if e['enabled'] and e['id']],
                         preview_status='鼓组键位映射待接入；可在鼓采样页选单个声音' if p['oscillator_mode']=='d' else '试听为原始波形，完整 Program DSP 待接入',
                         unresolved_layers=unresolved,recommended=p['bank_program'] in RECOMMENDED,
                         source_file=p['program_file'],source_sha256=p['program_sha256']))
    assert len(rows)==768 and len(waves)==489 and len(drums)==965
    assert not any(r['unresolved_layers'] for r in rows)
    data=dict(ROM_sha256=ROM_SHA,programs=rows,waveforms=waves,drums=drums,
              counts=dict(factory_samples=4068,diagnostics=2,multisample_records=496,waveform_auditions=len(waves),
                          drum_records=1014,drum_auditions=len(drums),factory_programs=len(rows),drum_programs=sum(r['oscillator_mode']=='d' for r in rows)),
              audition=dict(format='48000 Hz PCM16 WAV; preview-only peak matching <=0.8, gain capped at8; 2ms fade-in and40ms fade-out',
                            phrase='C3 G3 C4 G4, then C4 E4 G4 chord; fixed generic gate, no native Program envelope/filters/FX',
                            pitch='Original integer CPU pitch setup at zero external modulation, includes per-region signed fine tuning and descriptor phase limits',
                            loop='Forward-sustain preview convention where flag0x10 is set; candidate final guard excluded from repeated segment. Reverse/restart modes not fully reconstructed.',
                            resampler='scipy.signal.resample_poly with ratio denominator<=512',maximum_resample_error_cents=audition.max_resample_error_cents),
              GM_scope='GM names remain in the previous reference catalog; no independent GM parameter bank recovered, so no invented mapping here')
    save(SELECTION/'rom-sound-catalog.json',data)
    save(DERIVED/'audition-catalog.json',data)
    write_catalog_files(data, manifest)


def write_catalog_files(data, manifest):
    rows, waves, drums = data['programs'], data['waveforms'], data['drums']
    csv_write(SELECTION/'factory-programs-with-audio.csv',[
        dict(**{k:r[k] for k in ('id','name','category','subcategory','oscillator_mode','preview_status')},
             waveform_ids='; '.join(r['waveform_ids']),waveform_names='; '.join(next(w['name'] for w in waves if w['id']==i) for i in r['waveform_ids']),
             effects='; '.join(r['effects']),layers=json.dumps(r['layers'],ensure_ascii=False)) for r in rows],
        ['id','name','category','subcategory','oscillator_mode','waveform_ids','waveform_names','effects','preview_status','layers'])
    for filename,items in [('rom-multisamples-with-audio.csv',waves),('rom-drums-with-audio.csv',drums)]:
        csv_write(SELECTION/filename,[{**r,'indices':';'.join(map(str,r['indices'])),'sample_ids':';'.join(map(str,r['sample_ids']))} for r in items],
                  ['id','name','indices','category','channels','sample_ids','preview','preview_seconds'])
    csv_write(OUTPUT/'samples.csv',manifest['samples'],['sample_id','role','file','encoding','flags','frames','effective_rate_hz','wav_rate_hz','loop_start_relative','peak','rms','wav_sha256'])
    template=(ROOT/'tools/templates/factory_rom_selection.html').read_text()
    embedded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    (SELECTION/'index.html').write_text(template.replace('__CATALOG_JSON__',embedded))
    recommendations=[]
    for id in RECOMMENDED:
        p=next(p for p in rows if p['id']==id)
        links='、'.join(f'[{next(w["name"] for w in waves if w["id"]==wid)}]({next(w["preview"] for w in waves if w["id"]==wid)})' for wid in p['waveform_ids'])
        recommendations.append(f'| {id} | {p["name"]} | {p["category"]} | {links} |')
    (SELECTION/'ROM_AUDIO_README.md').write_text('''# 原机 ROM 试听与音色选择

打开 [带搜索、试听、勾选的音色表](index.html)。先在「预制音色」挑 A000 等编号，试听按钮播放该音色使用的原始波形。可切换到全部波形或鼓采样；勾选保存在本机浏览器，可复制或下载选择清单。

## 本次导出

- 4,068 个原机采样的完整 PCM24 WAV：[采样目录](../Factory_ROM_WAV/samples/)，[逐采样表](../Factory_ROM_WAV/samples.csv)。另外 2 个诊断波形单独存放。
- 496 条 Multisample 记录，合并 7 对 L/R 后为 489 项可试听波形。
- 1,014 条鼓采样记录，合并 49 对 L/R 后为 965 项可试听声音。
- A–F 共 768 个原厂 Program 的名称、分类、波形关联、力度层与效果器清单；其中 42 个鼓组 Program 的键位映射仍待接入。GM 名称保留在旧参考表，本次没有编造其独立参数映射。

## 试听含义

这是用于选素材的原始波形试听。四个单音和一个和弦采用通用门控与淡出；播放速率包含原固件分区音高修正。试听做了峰值匹配，原始采样 WAV 未做归一化。尚未给这 768 个 Program 重建完整的滤波、包络、AMS、LFO 和效果链，因此不能把试听当作预制音色成品。循环采用前向延音约定，反向/重启状态还需后续研究；完整原始字节和参数均已保留。

## 建议先挑这些

| 编号 | 原厂音色 | 分类 | 原始波形试听 |
|---|---|---|---|
'''+ '\n'.join(recommendations)+'''

## 可复用数据

- [768 项音色表 CSV](factory-programs-with-audio.csv)
- [波形 CSV](rom-multisamples-with-audio.csv)、[鼓采样 CSV](rom-drums-with-audio.csv)
- [完整映射 JSON](rom-sound-catalog.json)、[解码清单](../Factory_ROM_WAV/manifest.json)
- 技术依据：`docs/ROM_DECODING.md`；工具：`tools/decode_factory_rom.py` 和 `tools/build_factory_rom_selection.py`。

本次未修改产品资源或播放器，也未复制、安装 VST3。原始 ROM 和历史研究输出保持不变。
''')
    print(json.dumps(data['counts']),flush=True)
    print('Maximum audition resample error (cents):',data['audition']['maximum_resample_error_cents'],flush=True)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog-only', action='store_true', help='Rebuild HTML/CSV from existing audition manifest without rerendering WAVs')
    args = parser.parse_args()
    if args.catalog_only:
        data=json.loads((SELECTION/'rom-sound-catalog.json').read_text())
        manifest=json.loads((OUTPUT/'manifest.json').read_text())
        assert data['ROM_sha256']==manifest['ROM_sha256']==ROM_SHA
        write_catalog_files(data,manifest)
    else:
        build()
