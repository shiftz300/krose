#!/usr/bin/env python3
"""Render the architecture paper and reproducible vector diagrams.

Run with Codex bundled Python (reportlab, Pillow, pypdf); Poppler on PATH or
--pdftoppm. Research documents only; no product build or network operations.
"""
import argparse
import hashlib
import html
import json
import re
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from reportlab import rl_config
from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon, Circle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
    Spacer, PageBreak, Table, TableStyle, Image, KeepTogether, Preformatted)
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
DOC=ROOT/'research/docs/architecture'
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage01'
INK='#18354A';BLUE='#265D82';TEAL='#237B78';GRAY='#647784';PALE='#EDF3F6';GOLD='#A66B27'


def fonts():
    pdfmetrics.registerFont(TTFont('PaperBody','/System/Library/Fonts/Supplemental/Songti.ttc',subfontIndex=6))
    pdfmetrics.registerFont(TTFont('PaperUI','/System/Library/Fonts/STHeiti Light.ttc',subfontIndex=0))
    pdfmetrics.registerFont(TTFont('PaperBold','/System/Library/Fonts/STHeiti Medium.ttc',subfontIndex=0))
    pdfmetrics.registerFontFamily('PaperBody',normal='PaperBody',bold='PaperBold',italic='PaperBody',boldItalic='PaperBold')


def label(d,x,y,text,size=11,color=INK,anchor='middle',font='PaperUI'):
    for n,line in enumerate(text.split('\n')):
        d.add(String(x,y-n*(size+6),line,fontName=font,fontSize=size,fillColor=colors.HexColor(color),textAnchor=anchor))


def box(d,x,y,w,h,title,sub='',accent=BLUE):
    d.add(Rect(x,y,w,h,rx=6,ry=6,fillColor=colors.white,strokeColor=colors.HexColor(accent),strokeWidth=1.2))
    d.add(Rect(x,y+h-5,w,5,fillColor=colors.HexColor(accent),strokeColor=None))
    label(d,x+w/2,y+h-25,title,12,accent)
    if sub:label(d,x+w/2,y+h-47,sub,10.5,GRAY)


def arrow(d,x1,y1,x2,y2,dashed=False,color=GRAY):
    d.add(Line(x1,y1,x2,y2,strokeColor=colors.HexColor(color),strokeWidth=1.2,strokeDashArray=[4,3] if dashed else None))
    import math
    a=math.atan2(y2-y1,x2-x1);s=6
    points=[x2,y2,x2-s*math.cos(a-.45),y2-s*math.sin(a-.45),x2-s*math.cos(a+.45),y2-s*math.sin(a+.45)]
    d.add(Polygon(points,fillColor=colors.HexColor(color),strokeColor=None))


def figure_files(pdftoppm):
    folder=DOC/'figures';folder.mkdir(parents=True,exist_ok=True)
    figures={}
    d=Drawing(680,470)
    label(d,340,445,'界面、控制与音源的分工',17)
    box(d,20,340,190,70,'面板、键盘与 MMI','页面 / 参数编辑 / 模式')
    box(d,245,340,190,70,'USB 与 MIDI','驱动任务 / 输入解析')
    box(d,470,340,190,70,'文件与 SD 服务','文件任务 / SD 驱动任务')
    for x in [115,340,565]:arrow(d,x,340,x,305)
    box(d,20,220,640,85,'C++ 应用对象与 RDAPI 消息层','CSync / CS / MMI / 声音控制 / Pattern / 录音',TEAL)
    arrow(d,185,220,185,190);arrow(d,500,220,500,190)
    box(d,20,112,310,78,'实时内核','11 静态任务 / 16 优先级 / 时间堆')
    box(d,350,112,310,78,'TG 控制接口','音高 / EG / Filter / 效果载荷',TEAL)
    arrow(d,505,112,505,84,dashed=True,color=GOLD)
    box(d,350,12,310,72,'TGi 音频执行','采样播放 / 滤波 / 效果处理',GOLD)
    label(d,170,59,'实线：已定位的模块联系\n虚线：音频执行细节待解',10,GRAY)
    figures['system-architecture']=d
    d=Drawing(680,510)
    label(d,340,485,'从应用向量到持续控制循环',17)
    stages=[('应用向量 / 000000','初始 LDR PC -> 2C86A4',BLUE),
            ('应用预初始化 / 2C6B3C','设 SP / 清零应用区 / 建立服务',BLUE),
            ('内核启动 / 2FB9D0','向量 / 时间事件 / 对象 / 调度',BLUE),
            ('任务 1 / 2B6FA8','176 初始化回调 / 管理器 / 120 控制槽',TEAL),
            ('Sync 对象 / vtable + 8','标准或诊断模式 -> 2B5440',TEAL)]
    for i,(t,s,c) in enumerate(stages):
        y=385-i*87;box(d,130,y,420,66,t,s,c)
        if i<4:arrow(d,340,y,340,y-20)
    label(d,340,16,'更早的引导、DDR 初始化和 MMU 配置仍待恢复',10,GOLD)
    figures['startup-flow']=d
    d=Drawing(680,355)
    label(d,340,331,'固定优先级 + 同级 FIFO',17)
    label(d,58,283,'优先级',11,GRAY)
    groups=[(0,'1 -> 5 -> 6'),(1,'7 -> 8'),(2,'2 -> 3 -> 4 -> 9 -> 10'),(3,'11')]
    for i,(pri,ids) in enumerate(groups):
        y=235-i*47
        d.add(Circle(58,y+12,15,fillColor=colors.HexColor(BLUE),strokeColor=None));label(d,58,y+8,str(pri),11,'#FFFFFF')
        box(d,98,y-6,330,39,'任务 '+ids,'',TEAL)
    label(d,530,261,'初始位图 000F',12,BLUE)
    label(d,530,231,'最低置位 -> 优先级 0\n队首 -> 任务 1',11)
    arrow(d,428,247,455,247)
    box(d,452,100,205,89,'上下文','TCB +18 = SP\nTCB +1C = PC')
    label(d,340,20,'图示为初始队列；后续阻塞、退出与动态优先级会改变状态',10,GOLD)
    figures['scheduler']=d
    d=Drawing(680,350)
    label(d,340,325,'控制更新与音频平滑的时间尺度',17)
    left,right=90,640
    label(d,18,263,'tick',11,anchor='start');label(d,18,185,'批次',11,anchor='start');label(d,18,96,'语音',11,anchor='start')
    d.add(Line(left,257,right,257,strokeColor=colors.HexColor(GRAY)))
    for i in range(17):
        x=left+(right-left)*i/16
        d.add(Line(x,251,x,263,strokeColor=colors.HexColor(GRAY)))
        if i%4==0:label(d,x,275,f'{i} ms',10,GRAY)
    for i in range(8):
        x=left+(right-left)*i/8;w=(right-left)/8-4
        d.add(Rect(x,157,w,45,fillColor=colors.HexColor(PALE),strokeColor=colors.HexColor(TEAL)))
        label(d,x+w/2,183,f'{i*15}-{i*15+14}',10,TEAL)
    arrow(d,left,132,right,132,color=TEAL);label(d,365,113,'8 批 × 15 槽 = 120 槽 / 名义 16 ms',12,TEAL)
    box(d,90,25,550,65,'一次语音控制更新','24 EG 内部单位 -> TG 目标 / 步长 -> 音频帧平滑',BLUE)
    figures['control-timeline']=d
    d=Drawing(680,470)
    label(d,340,444,'事件、参数与音频数据流',17)
    box(d,18,334,192,72,'演奏输入','键盘 / MIDI / 音乐事件')
    box(d,244,334,192,72,'参数与 Pattern','Program / Kit / 模式 / 编辑')
    box(d,470,334,192,72,'存储后端','USB 系统卷 / SPI / TG ROM')
    arrow(d,114,334,114,295);arrow(d,340,334,340,295);arrow(d,566,334,566,295)
    box(d,18,211,418,84,'ARM 控制层','事件分发 -> 分配 / 音高 / 包络 / 调制',TEAL)
    box(d,470,211,192,84,'目录与采样','已冻结 PCM / 区域描述',TEAL)
    arrow(d,227,211,227,162);arrow(d,566,211,566,162)
    box(d,18,81,644,81,'TG / TGi 音频处理','控制寄存器 + 48 位效果上传 + 采样读取',BLUE)
    arrow(d,340,81,340,45,dashed=True,color=GOLD)
    label(d,340,20,'音频输出（插值、滤波及 DSP 算法仍待恢复）',11,GOLD)
    figures['data-flow']=d
    with tempfile.TemporaryDirectory(prefix='krose-architecture-figures-') as tmp:
        tmp=Path(tmp)
        config=tmp/'fonts.conf'
        config.write_text(f'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>/System/Library/Fonts</dir><cachedir>{tmp}/fontcache</cachedir></fontconfig>')
        env=dict(os.environ,FONTCONFIG_FILE=str(config))
        for name,drawing in figures.items():
            renderSVG.drawToFile(drawing,str(folder/(name+'.svg')))
            pdf=tmp/(name+'.pdf');renderPDF.drawToFile(drawing,str(pdf))
            subprocess.run([pdftoppm,'-png','-singlefile','-r','160',str(pdf),str(folder/name)],check=True,capture_output=True,env=env)
    shutil.copyfile(ROOT/'research/external/hardware/kross2-klm3665-listing.png',folder/'board-reference.png')


def inline(s):
    s=html.escape(s)
    s=re.sub(r'`([^`]+)`',r'<font name="PaperUI" size="8.5">\1</font>',s)
    s=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',r'<link href="\2" color="#265D82">\1</link>',s)
    return s


class Paper(BaseDocTemplate):
    def __init__(self,path):
        super().__init__(str(path),pagesize=(595.276,841.89),leftMargin=52,rightMargin=52,
                         topMargin=54,bottomMargin=48,title='KROSS 2 固件逆向报告',author='Krose firmware research',
                         subject='Official v1.2.4, stage 01; reproducible offline architecture research')
        self.addPageTemplates(PageTemplate(id='paper',frames=[Frame(52,48,491.276,739.89,id='main',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=self.page_header))
    def page_header(self,c,doc):
        c.saveState()
        if doc.page>1:
            c.setFont('PaperUI',8);c.setFillColor(colors.HexColor(GRAY))
            c.drawString(52,812,'KROSS 2 固件逆向报告')
            c.drawRightString(543,812,'v1.2.4 / 2026-11-01')
            c.setStrokeColor(colors.HexColor('#DCE5EB'));c.line(52,802,543,802)
        c.setFont('PaperUI',8);c.setFillColor(colors.HexColor(GRAY))
        c.drawString(52,28,'代码地址默认采用应用镜像文件偏移')
        c.drawRightString(543,28,str(doc.page))
        c.restoreState()
    def afterFlowable(self,f):
        if isinstance(f,Paragraph) and f.style.name=='H1':
            text=f.getPlainText();key=f'h{self.seq.nextf("heading")}'
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text,key,0,False)
            self.notify('TOCEntry',(0,text,self.page,key))


def render_paper():
    style={
        'Body':ParagraphStyle('Body',fontName='PaperBody',fontSize=10.2,leading=17,spaceAfter=8,wordWrap='CJK',textColor=colors.HexColor(INK)),
        'H1':ParagraphStyle('H1',fontName='PaperBold',fontSize=17,leading=24,spaceBefore=17,spaceAfter=12,keepWithNext=True,textColor=colors.HexColor(BLUE),wordWrap='CJK'),
        'H2':ParagraphStyle('H2',fontName='PaperBold',fontSize=12.5,leading=20,spaceBefore=12,spaceAfter=8,keepWithNext=True,textColor=colors.HexColor(INK),wordWrap='CJK'),
        'Reference':ParagraphStyle('Reference',fontName='PaperBody',fontSize=8.5,leading=13,spaceAfter=6,wordWrap='CJK',textColor=colors.HexColor(INK)),
        'Caption':ParagraphStyle('Caption',fontName='PaperUI',fontSize=8.5,leading=13,alignment=TA_CENTER,spaceAfter=10,textColor=colors.HexColor(GRAY),wordWrap='CJK'),
        'Cell':ParagraphStyle('Cell',fontName='PaperUI',fontSize=8.4,leading=13,wordWrap='CJK',textColor=colors.HexColor(INK)),
        'Code':ParagraphStyle('Code',fontName='PaperUI',fontSize=8,leading=13,spaceBefore=5,spaceAfter=9,backColor=colors.HexColor(PALE),borderPadding=8),
        'Title':ParagraphStyle('Title',fontName='PaperBold',fontSize=23,leading=32,textColor=colors.HexColor(INK),wordWrap='CJK'),
    }
    source=(DOC/'REPORT.md').read_text();lines=source.splitlines();story=[]
    story += [Paragraph('KROSS 2 固件逆向报告',style['Title']),Spacer(1,7),
        Paragraph('v1.2.4 · 2026-11-01',style['Caption']),
        Paragraph(inline(next(l for l in lines if l.startswith('**摘要**'))),style['Body'])]
    i=0;started=False;references=False
    while i<len(lines):
        l=lines[i].strip()
        if l.startswith('## 1 '):started=True
        if not started:i+=1;continue
        if not l:i+=1;continue
        if l.startswith('## '):
            if l == '## 证据索引与参考资料': references=True
            story.append(Paragraph(inline(l[3:]),style['H1']));i+=1;continue
        if l.startswith('### '):
            story.append(Paragraph(inline(l[4:]),style['H2']));i+=1;continue
        if l.startswith('```'):
            code=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                code.append(lines[i]);i+=1
            # Long hashes fit with a slightly smaller monospace-like UI font.
            story.append(Preformatted('\n'.join(code),style['Code'],maxLineLength=95));i+=1;continue
        if l.startswith('!['):
            m=re.match(r'!\[([^]]+)\]\(([^)]+)\)',l);p=DOC/m[2]
            image=ImageReader(str(p));w,h=image.getSize();scale=min(491/w,(320 if 'system-architecture' in p.name else 260)/h)
            flow=Image(str(p),width=w*scale,height=h*scale)
            story.append(KeepTogether([Spacer(1,7),flow,Spacer(1,5),Paragraph(m[1],style['Caption'])]));i+=1;continue
        if l.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                cells=[c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',c) for c in cells):rows.append(cells)
                i+=1
            n=len(rows[0]);widths=[491/n]*n
            if n==3:widths=[120,180,191]
            if n==4:widths=[80,122,110,179]
            if n==5:widths=[26,62,91,58,254]
            data=[[Paragraph(inline(c),style['Cell']) for c in row] for row in rows]
            t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT',splitByRow=0)
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DDE9EF')),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F5F8FA')]),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
                ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                ('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#B5CAD6'))]))
            story.extend([t,Spacer(1,10)]);continue
        if l.startswith('- '):
            story.append(Paragraph(inline(l[2:]),style['Reference'] if references else style['Body'],bulletText='•'));i+=1;continue
        paragraph=[l];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','```','![','- ')):
            paragraph.append(lines[i].strip());i+=1
        body_style = style['Reference'] if references else style['Body']
        following = next((x.strip() for x in lines[i:] if x.strip()), '')
        if following.startswith(('|','```')):
            body_style = ParagraphStyle('Lead',parent=body_style,keepWithNext=True)
        story.append(Paragraph(inline(' '.join(paragraph)),body_style))
    path=DOC/'KROSS2-v1.2.4-architecture-report.pdf'
    Paper(path).multiBuild(story)
    reader=PdfReader(path)
    text='\n'.join(p.extract_text() or '' for p in reader.pages)
    assert len(reader.pages)>=10 and '65,535' in text and '附录' in text
    assert all((p.extract_text() or '').strip() for p in reader.pages)
    (OUT/'report-check.json').write_text(json.dumps(dict(pdf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        markdown_sha256=hashlib.sha256((DOC/'REPORT.md').read_bytes()).hexdigest(),pages=len(reader.pages),
        text_characters=len(text),text_extraction_passed=True,visual_review='pending external page rendering',
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2)+'\n')
    print(json.dumps(dict(pdf=str(path),pages=len(reader.pages),characters=len(text)),ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdftoppm',default=shutil.which('pdftoppm'))
    args=parser.parse_args()
    if not args.pdftoppm:raise SystemExit('Pass --pdftoppm with the bundled Poppler executable')
    fonts();figure_files(args.pdftoppm);render_paper()


if __name__=='__main__':main()
