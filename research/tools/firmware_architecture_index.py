#!/usr/bin/env python3
"""Version-locked offline architecture index. No device APIs and no JIT.

Writes only architecture/stage01. Existing catalog and verification snapshots
are inputs. Recovered names are analyst aliases, not original debug symbols.
"""
import argparse
import collections
import contextlib
import csv
import hashlib
import io
import json
import platform
import re
import struct
import sys
from pathlib import Path

from program_firmware import Firmware, BASE, FW_SHA
from layout import PRODUCT_ROOT as ROOT
from firmware_inspect import inspect

OUT = ROOT / 'research/derived/firmware/KROSS2_V124/architecture/stage01'
CAT = ROOT / 'research/derived/firmware/KROSS2_V124/catalog/index.json'
# Names below are explicitly curated, not assigned by a pattern scanner.
NAMES = {
    0x2C86A4: ('application_vector_entry', 'boot', 'static'),
    0x2C86B0: ('application_fallback_entry', 'boot', 'static'),
    0x2C6B3C: ('application_pre_kernel_initialize', 'boot', 'static'),
    0x2C6BA4: ('unexpected_return_fatal', 'diagnostics', 'static'),
    0x2FB9D0: ('kernel_start', 'kernel', 'JSP source correspondence'),
    0x2FBB0C: ('cpu_vector_initialize', 'kernel', 'static'),
    0x2FB9B0: ('kernel_object_initialize', 'kernel', 'JSP source correspondence'),
    0x2FBB98: ('task_initialize', 'kernel', 'JSP source correspondence'),
    0x2FBCAC: ('task_make_dormant', 'kernel', 'JSP source correspondence'),
    0x2FBCE0: ('task_make_active', 'kernel', 'JSP ARMv4 source correspondence'),
    0x2FCEC0: ('task_make_runnable', 'kernel', 'JSP source correspondence'),
    0x2FCF44: ('task_make_non_runnable', 'kernel', 'JSP source correspondence'),
    0x2FD724: ('task_search_schedtsk', 'kernel', 'JSP source correspondence'),
    0x2FCD30: ('dispatch_save_context', 'kernel', 'JSP ARMv4 source correspondence'),
    0x2FCD78: ('exit_and_dispatch', 'kernel', 'JSP ARMv4 source correspondence'),
    0x2FCD9C: ('dispatcher_select_context', 'kernel', 'JSP ARMv4 source correspondence'),
    0x2FCDF8: ('activate_r', 'kernel', 'JSP ARMv4 source correspondence'),
    0x2FCE14: ('ret_int_dispatch', 'kernel', 'JSP ARMv4 source correspondence'),
    0x2FC9F0: ('get_tim', 'kernel', 'JSP source correspondence'),
    0x2FCA5C: ('get_tid', 'kernel', 'JSP source correspondence'),
    0x2FBD20: ('tmevt_initialize', 'kernel', 'JSP source correspondence'),
    0x2FBD5C: ('signal_time', 'kernel', 'JSP source correspondence'),
    0x2FD18C: ('make_wait_tmout', 'kernel', 'JSP source correspondence'),
    0x2FD58C: ('tmevtb_insert', 'kernel', 'JSP source correspondence'),
    0x2FD5D8: ('tmevtb_delete', 'kernel', 'JSP source correspondence'),
    0x2FD7C4: ('tmevt_up', 'kernel', 'JSP source correspondence'),
    0x2FD4CC: ('tmevt_down', 'kernel', 'JSP source correspondence'),
    0x2FC3CC: ('semaphore_initialize', 'kernel', 'JSP source correspondence'),
    0x2FC5C8: ('eventflag_initialize', 'kernel', 'JSP source correspondence'),
    0x2FCACC: ('interrupt_initialize', 'kernel', 'static'),
    0x2FCB30: ('irq_entry', 'kernel', 'static'),
    0x2CD184: ('RDAPI_current_task_id', 'ipc', 'static'),
    0x2CD2A0: ('RDAPI_task_priority_wrapper', 'ipc', 'static'),
    0x2CD6D0: ('RDAPI_set_task_delay', 'ipc', 'static'),
    0x2CD704: ('RDAPI_wait_task_event', 'ipc', 'static'),
    0x2CD744: ('RDAPI_get_time', 'ipc', 'static'),
    0x2CD764: ('RDAPI_signal_time', 'ipc', 'static'),
    0x2CD798: ('RDAPI_global_object_constructor', 'ipc', 'static'),
    0x2CD7AC: ('RDAPI_message_queue_append', 'ipc', 'static'),
    0x2CD7F4: ('RDAPI_message_queue_pop', 'ipc', 'static'),
    0x2CD694: ('RDAPI_pool_release', 'ipc', 'static'),
    0x2B6FA8: ('task01_system_initialize_then_sync', 'system', 'table + static'),
    0x04A38C: ('task02_cs_entry', 'system', 'table + source path'),
    0x14D75C: ('task03_mmi_entry', 'ui', 'table + CStandardMMI/CDiagnosticMMI RTTI'),
    0x0CDE1C: ('task04_filesystem_entry', 'storage', 'table + source path'),
    0x2CC864: ('task05_usb_driver_entry', 'usb', 'table + CUsbDrv RTTI'),
    0x2CCD08: ('task06_usb_midi_input_entry', 'usb', 'table + CUsbMIDIIn RTTI'),
    0x26C128: ('task07_sdcard_driver_entry', 'storage', 'table + source path'),
    0x01BB10: ('task08_diagnostic_audio_IO', 'audio', 'table + CDiagnosticAudiioIO RTTI; mode guard'),
    0x01BDD0: ('task09_SosProcess_entry', 'audio', 'table + SosProcess RTTI; mode guard'),
    0x01BCC4: ('task10_SosMainCtrl_entry', 'audio', 'table + SosMainCtrl RTTI; mode guard'),
    0x01BC2C: ('task11_periodic_audio_callbacks', 'audio', 'table + static; callback semantics unresolved'),
    0x2B5440: ('CSync_run', 'music_control', 'CSync-family vtable + static'),
    0x2B5AA0: ('CStandardSync_constructor', 'music_control', 'RTTI + static'),
    0x2B5B90: ('CDiagnosticSync_constructor', 'music_control', 'RTTI + static'),
    0x143E1C: ('CStandardMMI_constructor', 'ui', 'RTTI + static'),
    0x143EE0: ('CDiagnosticMMI_constructor', 'ui', 'RTTI + static'),
    0x143B30: ('CMMI_run', 'ui', 'MMI-family virtual slot + static'),
    0x2CA8C0: ('CUsbDrv_constructor', 'usb', 'RTTI + static'),
    0x2CAAA4: ('CUsbDrv_run', 'usb', 'virtual slot + static'),
    0x2CCC14: ('CUsbMIDIIn_constructor', 'usb', 'RTTI + static'),
    0x2CCCA8: ('CUsbMIDIIn_run', 'usb', 'virtual slot + static'),
    0x271324: ('sound_system_control_update', 'music_control', 'static + historical timing evidence'),
    0x1FD1C8: ('pcm_voice_manager_constructor', 'voice', 'historical ARM + static'),
    0x1FD3CC: ('pcm_voice_manager_control_slice', 'voice', 'historical ARM'),
    0x117064: ('timer0_tick_handler', 'hardware', 'static + historical ARM'),
    0x130620: ('timer0_program_period', 'hardware', 'historical ARM'),
    0x132660: ('interrupt_mask_save', 'hardware', 'static'),
    0x132670: ('interrupt_mask_restore', 'hardware', 'static'),
    0x14E5A4: ('memory_pool_initialize', 'memory', 'static'),
    0x14E730: ('checked_allocate', 'memory', 'static'),
    0x2C5220: ('system_error_dispatch', 'diagnostics', 'source strings + static'),
    0x2C6CD4: ('lcd_framebuffer_pixel_read', 'ui', 'static'),
    0x2C6D18: ('lcd_240x64_bitmap_copy', 'ui', 'static'),
    0x2C2E90: ('midi_exclusive_byte_parser', 'midi', 'historical ARM'),
    0x2C11A0: ('midi_message_dispatch', 'midi', 'historical ARM'),
    0x2BF1F4: ('midi_pcm_request_dispatch', 'midi', 'historical ARM'),
    0x2BD190: ('diagnostic_event_dispatch', 'diagnostics', 'historical ARM'),
}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def cfg(fw, entry, trusted):
    """Bounded intraprocedural traversal; unresolved control flow stays explicit.

    BL targets are recorded, not followed. Cross-entry B is a tail candidate.
    MOV LR,PC + indirect PC-write is a call, otherwise a terminal exit.
    Exception landing pads and jump tables are NOT invented by fallthrough.
    """
    pending = [entry]
    seen, edges, literals, unresolved = {}, [], [], []
    while pending and len(seen) < 8192:
        o = pending.pop()
        if o in seen or not 0 <= o < 0x330000 or abs(o-entry) > 0x10000:
            continue
        ins = next(MD.disasm(fw.data[o:o+4], BASE+o), None)
        if ins is None:
            unresolved.append({'offset': o, 'reason': 'undecodable'})
            continue
        w = fw.u32(o)
        seen[o] = (ins.mnemonic, ins.op_str)
        cond = w >> 28
        if w & 0x0F7F0000 == 0x051F0000:
            p = o+8+(1 if w & (1 << 23) else -1)*(w & 4095)
            if 0 <= p <= len(fw.data)-4:
                literals.append({'instruction': o, 'literal_offset': p, 'value': fw.u32(p)})
        if w & 0x0E000000 == 0x0A000000 and cond != 15:
            rel = w & 0xFFFFFF
            if rel & 0x800000:
                rel -= 1 << 24
            target = o+8+4*rel
            if w & 0x01000000:
                edges.append({'site': o, 'target': target, 'kind': 'direct_BL', 'condition': cond})
                pending.append(o+4)
            else:
                if target in trusted and target != entry:
                    edges.append({'site': o, 'target': target, 'kind': 'cross_entry_B_tail_candidate', 'condition': cond})
                else:
                    pending.append(target)
                if cond != 14:
                    pending.append(o+4)
            continue
        # Capstone handles aliases (POP/LDM/MOV/BX) and their PC writes.
        reads, writes = ins.regs_access()
        pc_written = PC_REG in writes or (ins.mnemonic.startswith(('ldm', 'pop')) and 'pc' in ins.op_str)
        if pc_written:
            previous = fw.u32(o-4) if o >= 4 else 0
            indirect_call = previous & 0x0FFFFFFF == 0x01A0E00F
            if indirect_call:
                edges.append({'site': o, 'target': None, 'kind': 'indirect_call', 'operand': ins.op_str})
                pending.append(o+4)
            elif cond != 14:
                pending.append(o+4)
            if not indirect_call and not ('lr' in ins.op_str or ins.mnemonic.startswith(('ldm', 'pop'))):
                unresolved.append({'offset': o, 'reason': 'indirect PC write / jump table', 'operand': ins.op_str})
        else:
            pending.append(o+4)
    return {'entry': entry, 'instruction_count': len(seen),
            'instruction_offsets': sorted(seen), 'edges': edges, 'literals': literals,
            'unresolved_exits': unresolved, 'scope': 'reachable bounded instructions; not complete function bounds'}


def rtti(fw):
    types = {}
    # Itanium C++ typeinfo layouts. Keep the encoded names verbatim.
    for o in range(0x330000, len(fw.data)-12, 4):
        if fw.u32(o) not in (BASE+0x482898, BASE+0x4828F4, BASE+0x482954):
            continue
        p = fw.u32(o+4)-BASE
        if not 0 <= p < len(fw.data):
            continue
        raw = fw.data[p:p+192].split(b'\0')[0]
        if not re.fullmatch(rb'[A-Za-z0-9_$]{2,180}', raw):
            continue
        name = raw.decode()
        if name[0].isdigit() or name.startswith(('N', 'St', 'P')):
            types[BASE+o] = {'typeinfo_offset': o, 'name_offset': p, 'encoded_name': name}
    vtables = []
    for o in range(0x330000, len(fw.data)-12, 4):
        if fw.u32(o) != 0 or fw.u32(o+4) not in types:
            continue
        slots = []
        p = o+8
        while p < len(fw.data)-4 and 0 <= fw.u32(p)-BASE < 0x330000 and len(slots) < 128:
            slots.append(fw.u32(p)-BASE)
            p += 4
        if slots:
            vtables.append({'address_point_offset': o+8, **types[fw.u32(o+4)], 'slots': slots,
                            'status': 'structural candidate; zero offset-to-top only; slot roles not automatic'})
    return list(types.values()), vtables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query', help='Search combined named entries, module paths and RTTI')
    parser.add_argument('--entry', type=lambda x: int(x, 0))
    parser.add_argument('--bytes', type=lambda x: int(x, 0), default=0x100)
    args = parser.parse_args()
    fw = Firmware()
    old = json.loads(CAT.read_text())
    types, vtables = rtti(fw)
    if args.entry is not None:
        print(NAMES.get(args.entry, 'No curated architecture alias'))
        inspect(fw.data, args.entry, args.entry+args.bytes)
        return
    if args.query:
        q = args.query.lower()
        for row in old['symbols'] + [dict(offset=o, name=v[0], module=v[1], status=v[2]) for o,v in NAMES.items()] + old['source_paths'] + types:
            if q in json.dumps(row).lower():
                print(json.dumps(row, ensure_ascii=False))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    import capstone
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
    from capstone.arm import ARM_REG_PC
    global MD, PC_REG
    MD = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    MD.detail = True
    PC_REG = ARM_REG_PC
    vectors = []
    for i,name in enumerate(['reset','undefined','swi','prefetch_abort','data_abort','reserved','irq','fiq']):
        o = i*4
        w = fw.u32(o)
        assert w & 0x0F7FF000 == 0x051FF000
        p = o+8+(1 if w & (1<<23) else -1)*(w & 4095)
        vectors.append(dict(name=name, offset=o, literal_offset=p, initial_target_offset=fw.u32(p)-BASE))
    tasks = []
    roles = [NAMES[fw.u32(0x459370+i*32+8)-BASE][0] for i in range(11)]
    for i in range(fw.u32(0x4594D0)):
        o = 0x459370+i*32
        atr, exinf, entry, pri, size, stack, texatr, texrtn = struct.unpack_from('<8I',fw.data,o)
        tasks.append(dict(task_id=i+1, config_offset=o, attributes=atr, auto_activate=bool(atr&2),
                          exinf=exinf, entry_offset=entry-BASE, virtual_entry=entry,
                          internal_priority=pri, public_priority=pri+1, stack_base=stack,
                          stack_bytes=size, stack_end_exclusive=stack+size, texatr=texatr,
                          texrtn=texrtn, tcb_address=0xC1B79EF4+i*32, analyst_role=roles[i]))
    assert len(tasks) == 11 and all(t['auto_activate'] for t in tasks)
    assert all(a['stack_end_exclusive'] == b['stack_base'] for a,b in zip(tasks,tasks[1:]))
    ctors = [dict(index=i, table_offset=o, target_offset=fw.u32(o)-BASE) for i,o in enumerate(range(0x482FD8,0x483298,4))]
    assert len(ctors) == 176 and all(0 <= c['target_offset'] < 0x330000 for c in ctors)
    resolved_objects = [
        ('CStandardSync',0x2B7864,0x2B5AA0,0x2B790C,0x4814B4,0x2B5440),
        ('CDiagnosticSync',0x2B7830,0x2B5B90,0x2B790C,0x4814E8,0x2B5440),
        ('CStandardMMI',0x14D868,0x143E1C,0x14D930,0x46EEA0,0x143B30),
        ('CDiagnosticMMI',0x14D840,0x143EE0,0x14D930,0x46EED8,0x143B30),
        ('CUsbDrv',0x2CC8BC,0x2CA8C0,0x2CC918,0x4819C4,0x2CAAA4),
        ('CUsbMIDIIn',0x2CCD60,0x2CCC14,0x2CCDBC,0x4819F0,0x2CCCA8)]
    # Callsite for CUsbDrv is checked against the bounded excerpt below by
    # actual instruction decoding, rather than presumed slot numbering.
    objects=[]
    for name,ctor_site,ctor,run_site,vt,run in resolved_objects:
        assert fw.u32(vt+8)==BASE+run
        w=fw.u32(ctor_site);rel=w&0xFFFFFF
        if rel&0x800000: rel-=1<<24
        assert w>>24==0xEB and ctor_site+8+4*rel==ctor
        assert fw.u32(run_site) in (0xE593F008,0xE1A0F002)
        objects.append(dict(class_name=name,constructor_callsite_offset=ctor_site,
            constructor_offset=ctor,run_callsite_offset=run_site,
            vtable_address_point_offset=vt,run_slot_byte_offset=8,run_entry_offset=run,
            status='manual object-flow resolution; base-constructor effects tested separately'))
    irqs = [dict(interrupt_id=fw.u32(o), attributes=fw.u32(o+4), entry_offset=fw.u32(o+8)-BASE,
                 table_offset=o) for o in range(0x459260,0x4592A8,12)]
    assert [r['interrupt_id'] for r in irqs] == [11,16,21,53,58,68]
    seeds = set(NAMES) | {t['entry_offset'] for t in tasks} | {c['target_offset'] for c in ctors} | {r['entry_offset'] for r in irqs}
    scopes = {o: cfg(fw,o,seeds) for o in sorted(seeds)}
    # A single expansion of actual reachable BL targets; no recursive claim.
    additional = {e['target'] for s in scopes.values() for e in s['edges'] if e['kind']=='direct_BL' and 0 <= e['target'] < 0x330000}
    trusted = seeds | additional
    for o in sorted(additional-seeds):
        scopes[o] = cfg(fw,o,trusted)
    merged = {r['offset']:dict(r) for r in old['symbols']}
    for o,(name,module,status) in NAMES.items():
        prior = merged.get(o)
        merged[o] = dict(offset=o, virtual_address=BASE+o, name=name, module=module,
                         status=status, previous_catalog_entry=prior)
    incoming = collections.defaultdict(list)
    for s in scopes.values():
        for e in s['edges']:
            if e['target'] is not None:
                incoming[e['target']].append(dict(scope_entry=s['entry'], **e))
    for o,item in merged.items():
        item['bounded_scope_incoming_edges'] = incoming[o]
    modules = collections.defaultdict(list)
    for row in old['source_paths']:
        m = row['path'].split('/source/')[-1].split('/')[0]
        modules[m].append(row)
    meta = dict(firmware_sha256=FW_SHA, image_bytes=len(fw.data), virtual_image_base=BASE,
                coordinate_system='All *_offset values are decompressed KROSSAPP.bin file offsets. Other *_address, virtual_*, stack_* values are virtual addresses.',
                tool_sha256=sha(Path(__file__).read_bytes()), python=platform.python_version(), capstone=capstone.__version__,
                input_catalog_sha256=sha(CAT.read_bytes()), analysis_stage='stage01', device_access=False,
                limitations=['No OS startup or hardware execution', 'RTTI/vtable scan is structural, excludes secondary vtables',
                             'Bounded CFG stops at unresolved jump tables and indirect exits; exception landing pads incomplete',
                             'No full image function recovery; linear legacy cross references remain candidates',
                             'JSP 1.4.4.1 is a comparison source, exact release unproven'])
    dump(OUT/'startup.json',dict(**meta, vectors=vectors,
        memory_clear=dict(start_address=0xC0A00000,end_address_exclusive=0xC1B7A464,bytes=0x117A464),
        entry_stack_address=0xC22B5B90, idle_stack_address=0xC22B9B8C,
        constructors=dict(start_offset=0x482FD8,end_offset_exclusive=0x483298, entries=ctors),
        tasks=tasks, interrupts=irqs, resolved_object_dispatch=objects,
        semaphore_count=fw.u32(0x459340), eventflag_count=fw.u32(0x459324),
        kernel=dict(tcb_bytes=32,tinib_bytes=32,ready_priority_levels=16,
                    runtsk_address=0xC1B7A3A0,schedtsk_address=0xC1B7A3A8,
                    ready_queue_address=0xC1B7A31C,ready_primap_address=0xC1B7A39C,
                    current_time_address=0xC1B7A3AC,next_time_address=0xC1B7A3B0,
                    time_heap_address=0xC1B79E9C,last_index_address=0xC1B7A3B8)))
    dump(OUT/'index.json',dict(**meta,symbols=list(sorted(merged.values(),key=lambda x:x['offset'])),
                             source_modules=dict(modules),rtti_types=types,vtables=vtables))
    dump(OUT/'bounded-cfg.json',dict(**meta,initial_seed_count=len(seeds),scope_count=len(scopes),
                                   scopes=list(sorted(scopes.values(),key=lambda x:x['entry']))))
    with (OUT/'symbols.csv').open('w',newline='') as stream:
        w=csv.writer(stream);w.writerow(['image_offset','virtual_address','analyst_name','evidence_status'])
        for row in sorted(merged.values(),key=lambda x:x['offset']):
            w.writerow([hex(row['offset']),hex(BASE+row['offset']),row['name'],row['status']])
    # Dedicated excerpts are bounded evidence, not whole-function decompilations.
    excerpts = [(0,0x3C),(0x2C86A4,0x2C86C0),(0x2C6B3C,0x2C6BB8),
        (0x2FB9D0,0x2FBA0C),(0x2FBB0C,0x2FBB68),(0x2FBB98,0x2FBD20),
        (0x2FCD30,0x2FCE88),(0x2FCEC0,0x2FCF44),(0x2FD724,0x2FD774),
        (0x2B6FE8,0x2B7084),(0x2B744C,0x2B74A4),(0x2B781C,0x2B7920),
        (0x2B5440,0x2B55A8),(0x117064,0x117144),(0x2FBD20,0x2FBEB8),
        (0x2FD18C,0x2FD1F8),(0x2FD58C,0x2FD5D8),(0x2CD7AC,0x2CD848),
        (0x2FC3CC,0x2FC41C),(0x2FC5C8,0x2FC618),(0x2C6CD4,0x2C6D74)]
    text=io.StringIO()
    with contextlib.redirect_stdout(text):
        print('Firmware SHA256:',FW_SHA,'; addresses are image file offsets')
        for start,end in excerpts:
            print(f'\n# bounded evidence excerpt [{start:#x},{end:#x})')
            inspect(fw.data,start,end)
    (OUT/'startup-scheduler.arm.txt').write_text(text.getvalue())
    dump(OUT/'static-check.json',dict(**meta,passed=True,checks=dict(
        vectors=8,tasks=11,constructors=176,interrupts=6,task_stacks_contiguous=True,
        stack_total_bytes=sum(t['stack_bytes'] for t in tasks),source_modules=len(modules),
        combined_symbols=len(merged),rtti_types=len(types),vtable_candidates=len(vtables),
        bounded_scopes=len(scopes))))
    print(json.dumps(json.loads((OUT/'static-check.json').read_text())['checks'],indent=2))


if __name__ == '__main__':
    main()
