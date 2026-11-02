#!/usr/bin/env python3
"""Plot independently checked drum pan targets and parameter timing."""
import csv,json
from firmware_runtime_figures import Canvas,BLUE,TEAL,GRAY,GOLD
from firmware_limiter_figures import axis
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    d=json.loads((OUT/'drum-controls-check.json').read_text());assert d['passed'] and not d['smoke_only']
    c=Canvas(930,500);c.text(465,13,'鼓组声像：左右采样使用不同控制位置',24)
    c.text(465,54,'通道与起音参考声像居中；每个点与原计算逐项比较，0 号随机位置单独处理',13,GRAY)
    xy=axis(c,100,130,710,245,[(1,'1'),(32,'32'),(64,'64'),(96,'96'),(127,'127')],
        [(256,'256'),(16384,'16384'),(32512,'32512')],lambda v:(v-1)/126,lambda v:(v-256)/32256)
    for pair,color,dash in [(0,GRAY,False),(1,BLUE,False),(2,TEAL,True)]:
        rows=sorted((x for x in d['pan']['positions'] if x['pair']==pair and x['position']>0),key=lambda x:x['position'])
        points=[xy(x['position'],x['pan']) for x in rows]
        for a,b in zip(points,points[1:]):c.line(*a,*b,color,2,dash)
    c.text(455,402,'逐键声像值',14,GRAY)
    for x,title,color,dash in [(180,'单声道',GRAY,False),(425,'立体声主侧',BLUE,False),(700,'立体声副侧',TEAL,True)]:
        c.line(x-60,453,x-30,453,color,2,dash);c.text(x+35,443,title,14,color)
    c.text(465,480,'纵轴为 TG 声像控制位置；声道增益曲线与实际音频仍需另行恢复。',12,GRAY)
    c.save('drum-control-pan')

    latch=d['latched_controls'];changed=latch['retrigger_changed'];baseline=latch['retrigger_baseline']
    trace=next(t for t in d['traces'] if (t['program'],t['note'],t['batch'])==('F042',48,8))
    later=next(row for step in trace['steps'] if 16<=step['update']<24 for row in step['pan'])
    c=Canvas(960,600);c.text(480,13,'参数写入后，何时影响鼓声',24)
    c.text(480,54,'原参数写入入口 → 原刷新管理器 → 原再次起音；F042 / Basic Kit 1，按键 48',13,GRAY)
    c.box(25,111,270,138,'起音时保存到声部',[
        '粗调 / 微调','滤波截止偏移 / 共振偏移',
        f"本例原值：调音 {baseline['voices'][0]['tune']}、偏移 {baseline['cutoff']} / {baseline['resonance']}",
        '后续刷新沿用已保存的状态'],BLUE)
    c.box(345,111,270,138,'修改逐键记录',[
        '调音 76 / 48；滤波 96 / 80','已有声部连续推进 32 次',
        '全部声部字节与基线相同','TG 读写顺序与值也相同'],GOLD)
    c.box(665,111,270,138,'再次起音读取新值',[
        f"新调音量：{changed['voices'][0]['tune']}",
        f"新截止偏移：{changed['cutoff']}",f"新共振偏移：{changed['resonance']}",'新声部独立核对原整数方程'],TEAL)
    c.arrow(295,180,345,180);c.arrow(615,180,665,180)
    c.box(120,322,720,132,'音量、声像与发送在持续刷新中读取',[
        f"逐键声像改为 96 后，本例下一次处理得到目标 {later['pan']}",
        '发送同时受逐键覆盖、通道缩放和路由抑制约束',
        '随机声像沿用该声部起音时生成的位置；重复刷新保持该位置',
        '这条路径的变化无需等待下一次起音'],BLUE)
    c.text(480,496,'结论适用于本轮逐键写入与正常刷新路径；其他编辑回调的副作用单独保留。',13,GRAY)
    c.text(480,543,'控制更新次数尚未换算为硬件时间；当前检查未生成声音。',12,GRAY)
    c.save('drum-control-timing')

    with (OUT/'drum-control-pan.csv').open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=['position','channel','part','use_key','pair','random','pan','send1','send2','previous_pan']);writer.writeheader();writer.writerows(d['pan']['positions'])
    with (OUT/'drum-control-refresh.csv').open('w',newline='') as out:
        fields=['program','note','batch','update','voice','amp','pitch','pan','send1','send2'];writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
        for trace in d['traces']:
            for step in trace['steps']:
                pans={row['voice']:row for row in step['pan']}
                for row in step['commits']:
                    pan=pans[row['voice']];writer.writerow(dict(program=trace['program'],note=trace['note'],batch=trace['batch'],update=step['update'],
                        voice=row['voice'],amp=row['amp'],pitch=row['pitch'],pan=pan['pan'],send1=pan['send1'],send2=pan['send2']))
    print('Rendered two drum-control figures (PNG/SVG), with pan and refresh CSV files.')
if __name__=='__main__':main()
