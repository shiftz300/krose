#!/usr/bin/env python3
"""Render the current plugin research paper without rewriting stage01."""
import argparse,hashlib,html,json,re,subprocess
from pathlib import Path
from reportlab.graphics.shapes import Drawing,Rect,Line,Polygon,String
from reportlab.graphics import renderSVG,renderPDF
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import BaseDocTemplate,Frame,PageTemplate,Paragraph,Spacer,PageBreak,Table,TableStyle,Image,KeepTogether,Preformatted
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader
from firmware_architecture_report import fonts
from layout import PRODUCT_ROOT as ROOT
DOC=ROOT/'research/docs/architecture';OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage05'
PDF=ROOT/'research/output/pdf/KROSS2-v1.2.4-plugin-report.pdf'
INK='#18354a';BLUE='#265d82';TEAL='#237b78';GRAY='#647784';GOLD='#a66b27'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inline(text):
    text=html.escape(text)
    text=re.sub(r'`([^`]+)`',r'<font name="PaperUI">\1</font>',text)
    text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
    return re.sub(r'\[([^]]+)\]\(([^)]+)\)',r'<font color="#265d82">\1</font>',text)
def overview():
    d=Drawing(491,253)
    def box(x,y,w,h,title,detail,color):
        d.add(Rect(x,y,w,h,rx=4,ry=4,strokeColor=colors.HexColor(color),fillColor=colors.white))
        for yy,s,size,col in [(y+h-19,title,11,color),(y+12,detail,8.8,GRAY)]:d.add(String(x+w/2,yy,s,fontName='PaperUI',fontSize=size,fillColor=colors.HexColor(col),textAnchor='middle'))
    def arrow(x,y,xx,yy):
        d.add(Line(x,y,xx,yy,strokeColor=colors.HexColor(GRAY)))
        d.add(Polygon([xx,yy,xx-3,yy+6,xx+3,yy+6],fillColor=colors.HexColor(GRAY),strokeColor=None))
    box(5,197,230,49,'演奏事件','MIDI / 琶音 / 鼓轨 / 步进',BLUE)
    box(256,197,230,49,'Program / Drum Kit','键区 / 力度 / 素材引用 / 参数',BLUE)
    box(5,127,230,49,'选层与声部分配','交叉权重 / 立体声 / 复用与释放',TEAL)
    box(256,127,230,49,'采样资源','银行 / Multisample / 区域 / PCM',TEAL)
    arrow(120,197,120,176);arrow(371,197,371,176)
    box(5,65,481,43,'控制计算：EG / LFO / AMS / 音高 / Filter A/B / Amp','原 ARM 运算、持续状态与控制目标',BLUE)
    arrow(120,127,120,108);arrow(371,127,371,108)
    box(5,3,481,43,'音频输出：采样播放 → 滤波 → 放大 / 声像 → IFX / MFX','插值、TG 滤波及部分效果音频仍有缺口',GOLD)
    arrow(245,65,245,46)
    return d
def paper_diagram(kind):
    d=Drawing(491,218 if kind=='factory' else 210)
    def text(x,y,s,size=10,color=INK):d.add(String(x,y,s,fontName='PaperUI',fontSize=size,fillColor=colors.HexColor(color),textAnchor='middle'))
    def box(x,y,w,h,title,lines,color=BLUE):
        d.add(Rect(x,y,w,h,rx=4,ry=4,fillColor=colors.white,strokeColor=colors.HexColor(color)))
        text(x+w/2,y+h-17,title,11,color)
        for i,s in enumerate(lines):text(x+w/2,y+h-34-14*i,s,9,GRAY)
    def link(x,y,xx,yy):
        d.add(Line(x,y,xx,yy,strokeColor=colors.HexColor(GRAY)))
    if kind=='factory':
        text(245,202,'A011 / OSC 1：音符 63，力度 105',11,BLUE)
        for x,title,gain,correction in [(5,'层 1',12477,-23),(256,'层 2',16254,0)]:
            box(x,115,230,65,title,[f'权重 16384；层电平缩放后 63',f'区域修正 {correction}；主侧增益 {gain}'],TEAL)
            for j,sample in enumerate([1619,1620] if x==5 else [1571,1572]):
                xx=x+120*j;box(xx,22,110,65,'主侧' if j==0 else '副侧',[f'Sample {sample}','计算控制' if j==0 else '复制共享控制'])
                link(x+115,115,xx+55,87)
        text(245,3,'四个声部各持采样地址；立体声两侧共享包络、滤波和音量状态',9,GRAY)
    else:
        for y,title,condition,rule in [(150,'用户鼓组','Drum 模式，旧号 ≥ 42','min(57, 旧号 - 42 + 目标起点)'),
                (85,'琶音 Pattern','旧号 ≥ 1029','min(1284, 旧号 - 1024 + 目标基数)'),
                (20,'关联 Program','来源区间内，起点 768','min(1279, 旧号 - 768 + 目标起点)')]:
            box(5,y,140,52,title,[condition],TEAL);link(145,y+26,160,y+26)
            box(160,y,326,52,rule,['区间外保留原值；上限截断可能合并引用'])
    return d
class Paper(BaseDocTemplate):
    def __init__(self,path):
        super().__init__(str(path),pagesize=(595.276,841.89),leftMargin=52,rightMargin=52,topMargin=54,bottomMargin=49,
            title='KROSS 2 音源逆向报告',author='Krose research',subject='v1.2.4 plugin logic; offline evidence and remaining audio gaps')
        self.addPageTemplates(PageTemplate(id='paper',frames=[Frame(52,49,491.276,738.89,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=self.header))
    def header(self,c,doc):
        c.saveState();c.setFont('PaperUI',8);c.setFillColor(colors.HexColor(GRAY))
        if doc.page>1:
            c.drawString(52,812,'KROSS 2 音源逆向报告');c.drawRightString(543,812,'v1.2.4 / 研究版 / 2026-11-02')
            c.setStrokeColor(colors.HexColor('#dce5eb'));c.line(52,802,543,802)
        c.drawString(52,28,'插件音源逻辑 / 离线原指令证据');c.drawRightString(543,28,str(doc.page));c.restoreState()
    def afterFlowable(self,f):
        if isinstance(f,Paragraph) and f.style.name=='Heading':
            title=f.getPlainText();key='h'+str(self.seq.nextf('heading'));self.canv.bookmarkPage(key);self.canv.addOutlineEntry(title,key,0)
def main():
    p=argparse.ArgumentParser();p.add_argument('--pdftoppm',required=True);args=p.parse_args();fonts();OUT.mkdir(parents=True,exist_ok=True);PDF.parent.mkdir(parents=True,exist_ok=True)
    s={
        'body':ParagraphStyle('Body',fontName='PaperBody',fontSize=10.5,leading=17,spaceAfter=8,wordWrap='CJK',textColor=colors.HexColor(INK)),
        'title':ParagraphStyle('Title',fontName='PaperBold',fontSize=23,leading=31,spaceAfter=8,textColor=colors.HexColor(INK)),
        'heading':ParagraphStyle('Heading',fontName='PaperBold',fontSize=16,leading=23,spaceBefore=9,spaceAfter=10,keepWithNext=True,textColor=colors.HexColor(BLUE)),
        'sub':ParagraphStyle('Sub',fontName='PaperBold',fontSize=11,leading=17,spaceBefore=7,spaceAfter=5,keepWithNext=True),
        'cell':ParagraphStyle('Cell',fontName='PaperUI',fontSize=8.6,leading=13.4,wordWrap='CJK',textColor=colors.HexColor(INK)),
        'caption':ParagraphStyle('Caption',fontName='PaperUI',fontSize=8.5,leading=13,alignment=1,spaceAfter=9,wordWrap='CJK',textColor=colors.HexColor(GRAY)),
        'reference':ParagraphStyle('Reference',fontName='PaperBody',fontSize=9,leading=13.5,spaceAfter=4,wordWrap='CJK',textColor=colors.HexColor(INK)),
        'code':ParagraphStyle('Code',fontName='PaperUI',fontSize=8,leading=12,spaceAfter=9,backColor=colors.HexColor('#edf3f6'),borderPadding=7)}
    source=DOC/'PLUGIN_REPORT.md';lines=source.read_text().splitlines();story=[];images=[];i=0
    drawings={'plugin-sound-flow':overview(),'plugin-factory-voices':paper_diagram('factory'),'plugin-import-references':paper_diagram('import')}
    for name,drawing in drawings.items():
        renderSVG.drawToFile(drawing,str(DOC/'figures'/(name+'.svg')));renderPDF.drawToFile(drawing,str(OUT/(name+'.pdf')))
        subprocess.run([args.pdftoppm,'-png','-singlefile','-r','180',str(OUT/(name+'.pdf')),str(DOC/'figures'/name)],check=True,capture_output=True)
    # Keep the source Markdown independently viewable.
    while i<len(lines):
        l=lines[i].strip();i+=1
        if not l:continue
        if l=='<!-- pagebreak -->':story.append(PageBreak());continue
        if l.startswith('# '):story.append(Paragraph(inline(l[2:]),s['title']));continue
        if l.startswith('## '):story.append(Paragraph(inline(l[3:]),s['heading']));continue
        if l.startswith('### '):story.append(Paragraph(inline(l[4:]),s['sub']));continue
        if l.startswith('!['):
            m=re.fullmatch(r'!\[([^]]+)\]\(([^)]+)\)',l);target=m[2]
            if Path(target).stem in drawings:flow=drawings[Path(target).stem];path=DOC/target
            else:
                path=DOC/target;w,h=ImageReader(str(path)).getSize();scale=min(491/w,252/h);flow=Image(str(path),width=w*scale,height=h*scale)
            images.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path)))
            story.append(KeepTogether([Spacer(1,5),flow,Spacer(1,5),Paragraph(m[1],s['caption'])]));continue
        if l.startswith('```'):
            code=[]
            while i<len(lines) and not lines[i].startswith('```'):code.append(lines[i]);i+=1
            i+=1;story.append(Preformatted('\n'.join(code),s['code']));continue
        if l.startswith('|'):
            raw=[l]
            while i<len(lines) and lines[i].strip().startswith('|'):raw.append(lines[i].strip());i+=1
            rows=[]
            for row in raw:
                cells=[c.strip() for c in row.strip('|').split('|')]
                if not all(re.fullmatch(':?-+:?',c) for c in cells):rows.append(cells)
            n=len(rows[0]);widths=[491/n]*n
            if n==3:widths=[90,205,196]
            if n==2:widths=[116,375]
            table=Table([[Paragraph(inline(c),s['cell']) for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dfeaf0')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f8fa')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
            story.extend([table,Spacer(1,9)]);continue
        if l.startswith('- '):story.append(Paragraph(inline(l[2:]),s['reference']));continue
        paragraph=[l]
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','```','![','- ','<!--')):paragraph.append(lines[i].strip());i+=1
        story.append(Paragraph(inline(' '.join(paragraph)),s['body']))
    Paper(PDF).build(story);reader=PdfReader(PDF);texts=[p.extract_text() or '' for p in reader.pages]
    assert len(texts)>=10 and all(len(t)>100 for t in texts)
    assert all(any(f'{n} ' in t for t in texts) for n in range(1,11))
    verification=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage02/verification.json';check=json.loads(verification.read_text());assert check['passed'] and len(check['current_checks'])==86
    refs=[]
    for target in re.findall(r'\[[^]]*\]\(([^)]+)\)',source.read_text()):
        path=(DOC/target).resolve();assert path.is_file();refs.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path)))
    data=dict(passed=True,pdf=dict(path=str(PDF.relative_to(ROOT)),sha256=sha(PDF)),markdown=dict(path=str(source.relative_to(ROOT)),sha256=sha(source)),pages=len(texts),page_characters=list(map(len,texts)),images=images,references=refs,arm_checks=check['current_checks'],host_audio_checks=check['host_audio_checks'],verification_sha256=sha(verification),tool_sha256=sha(Path(__file__)),font_helper_sha256=sha(ROOT/'research/tools/firmware_architecture_report.py'),visual_review='pending',scope='Current research paper; incomplete audio algorithms explicitly identified; stage01 unchanged')
    (OUT/'plugin-report-check.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(dict(pdf=str(PDF),pages=len(texts),characters=sum(map(len,texts))),ensure_ascii=False))
if __name__=='__main__':main()
