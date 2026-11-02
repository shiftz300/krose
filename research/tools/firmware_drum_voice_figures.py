#!/usr/bin/env python3
"""Draw source-backed factory drum assembly, exclusivity and note-off results."""
import csv,hashlib,json
from pathlib import Path
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    d=json.loads((OUT/'drum-voice-chain-check.json').read_text());assert d['passed'] and not d['smoke_only']
    source=ROOT/d['inputs'][0]['path'];raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==d['inputs'][0]['sha256']
    used={(x['kit'],v['key'],v['slot']) for x in d['factory'] for v in x['voices']};stored=set();unreachable=[];key_flags={}
    for kit in d['kits']:
        for key in kit['assigned_keys']:
            start=0x48BE20+8728*kit['kit']+24+68*key;k=raw[start:start+68];key_flags[kit['kit'],key]=k[65]
            for slot in range(4):
                if not k[12*slot]&1:continue
                identity=(kit['kit'],key,slot);stored.add(identity)
                if identity in used:continue
                selected=[]
                for velocity in range(1,128):
                    first=next((i for i in range(3) if velocity>=k[48+4*i]),3);slots=[first]
                    if first<3 and k[49+4*first] and velocity<k[48+4*first]+k[49+4*first]:slots.append(first+1)
                    if slot in slots:selected.append(velocity)
                assert not selected,(identity,selected)
                unreachable.append(dict(program=kit['program'],kit=kit['kit'],note=key,slot=slot,threshold_bytes=list(k[48:60]),
                    reason='All nonzero velocities select slot 0; no overlap is enabled'))
    assert len(stored)==5239 and len(used)==5237 and stored-used=={(x['kit'],x['note'],x['slot']) for x in unreachable}
    assert sum(bool(flags&8) for flags in key_flags.values())==11
    coverage=dict(passed=True,tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        check_sha256=hashlib.sha256((OUT/'drum-voice-chain-check.json').read_bytes()).hexdigest(),preload_sha256=hashlib.sha256(raw).hexdigest(),
        stored_enabled_slots=len(stored),initialized_slots=len(used),unreachable_enabled_slots=unreachable,
        key_note_off_enabled=sum(bool(flags&8) for flags in key_flags.values()),key_note_off_disabled=sum(not flags&8 for flags in key_flags.values()))
    (OUT/'drum-voice-coverage.json').write_text(json.dumps(coverage,indent=2)+'\n')
    example=next(x for x in d['factory'] if (x['program'],x['note'],x['velocity'])==('F033',24,100));v=example['voices'][0]
    c=Canvas(930,590);c.text(465,13,'鼓组怎样找到真正播放的采样',24)
    c.text(465,54,'原厂 F033 / Rock Kit 1，按键 24、力度 100；整条原 ARM 控制链执行',13,GRAY)
    blocks=[(25,103,260,112,'Program → Drum Kit',['OSC 选择鼓组 2','128 个按键，各占 68 字节','空键向上寻找下一分配键'],BLUE),
            (335,103,260,112,'按键 → 力度层',[f"按键 {v['key']}，第 {v['slot']+1} 层",'四个候选层，最多同时取两层',f"当前权重 {v['weight']} / 32768"],BLUE),
            (645,103,260,112,'鼓采样目录 → PCM',[f"Drumsample {v['drumsample']}",f"Sample {v['sample']}",'左右配对来自原生目录构造'],TEAL)]
    for x,y,w,h,title,lines,color in blocks:c.box(x,y,w,h,title,lines,color)
    c.arrow(285,159,335,159);c.arrow(595,159,645,159)
    c.arrow(775,215,775,271);c.arrow(775,271,465,271);c.arrow(465,271,465,315)
    c.box(210,315,510,136,'两项有符号修正共同决定中间增益',[
        f"交叉缩放后的层电平：{v['layer_level']}",
        f"鼓组描述符修正 {v['level_correction']}，鼓采样目录修正 {v['max_level']}",
        f"原整数结果 G = {v['gain']}；后续仍叠加力度、调制与包络",'采样根音固定为 60，调音来自每层的粗调与微调'],GOLD)
    c.text(465,488,'鼓组层电平与旋律音色的处理方式不同，不能共用旋律描述符的缩放规则。',14,BLUE)
    c.text(465,534,'模式、起始、结束和循环命令已与原样本字节逐项核对；本轮未渲染音频。',12,GRAY)
    c.save('drum-voice-resource-path')

    seq=next(x for x in d['choke_sequences'] if x['program']=='F042' and x['group']==2)
    a,b=seq['first'],seq['second'];c=Canvas(930,590);c.text(465,13,'截音与松键是两条独立规则',24)
    c.text(465,54,'Basic Kit 1：按键 54、56、58 共用独占组 2；新音截断同组旧音',13,GRAY)
    c.box(40,109,350,116,f"第一次起音：按键 {a['note']}",[
        f"建立 {len(a['voices'])} 个声部",f"活动槽：{', '.join(map(str,a['active']))}",'音符挂入 OSC 活动列表'],BLUE)
    c.box(540,109,350,116,f"第二次起音：按键 {b['note']}",[
        f"硬停止旧槽：{', '.join(map(str,b['hardstops']))}",f"存活槽：{', '.join(map(str,b['active']))}",'若旧音为立体声，两侧一起停止'],TEAL)
    c.arrow(390,167,540,167,GOLD)
    c.text(465,256,'独占组 0 允许叠加；非零组在新音挂入列表前清理旧音。',14,BLUE)
    c.box(40,327,400,119,'多数鼓键：松键后继续衰减',[
        'Program Hold 开启，按键未启用 Note Off',
        '松键清除按下标志，保持原音量包络','3583 个原厂分配键保存这一配置'],BLUE)
    c.box(490,327,400,119,'Human Beat Box：部分键允许释音',[
        '11 个分配键启用 Note Off 接收',
        '松键进入原释放分支并提交控制',
        '释放允许位已逐个启动上下文核对'],TEAL)
    c.text(465,492,f"连续截音：{len(d['choke_sequences'])} 组；松键代表上下文：{len(d['release_cases'])} 组。",14,BLUE)
    c.text(465,537,'图示为原控制与命令结果；样本尾音和硬件衰减时长尚未作为音频比较。',12,GRAY)
    c.save('drum-voice-choke-release')

    with (OUT/'drum-voice-chain.csv').open('w',newline='') as out:
        writer=csv.writer(out);columns=['key','layer','side','slot','weight','drumsample','sample','pair_type','layer_level','level_correction','max_level','gain',
                                      'tune','reverse','release','exclusive','start_offset','pan_target','amp_target','pitch_increment']
        writer.writerow(['program','kit','note','velocity',*columns])
        for item in d['factory']:
            for v in item['voices']:writer.writerow([item['program'],item['kit'],item['note'],item['velocity'],*[v[k] for k in columns]])
    with (OUT/'drum-voice-remap.csv').open('w',newline='') as out:
        writer=csv.writer(out);writer.writerow(['program','kit','note','distance','target','assigned'])
        for kit in d['kits']:
            for note,distance in enumerate(kit['remap']):writer.writerow([kit['program'],kit['kit'],note,distance,None if distance<0 else note+distance,note in kit['assigned_keys']])
    print('Rendered two drum voice figures (PNG/SVG), with startup and remap CSV files.')
if __name__=='__main__':main()
