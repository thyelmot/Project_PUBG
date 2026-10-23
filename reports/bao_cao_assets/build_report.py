from pathlib import Path
import re,html,json
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER,TA_JUSTIFY,TA_LEFT
from reportlab.lib import colors
from reportlab.platypus import BaseDocTemplate,PageTemplate,Frame,Paragraph,Spacer,PageBreak,Image,Table,TableStyle,KeepTogether
from reportlab.platypus.tableofcontents import TableOfContents
import pdfplumber
ROOT=Path(__file__).resolve().parents[1];A=Path(__file__).resolve().parent
for name,file in [('TimesVN','Times New Roman.ttf'),('TimesVN-Bold','Times New Roman Bold.ttf'),('TimesVN-Italic','Times New Roman Italic.ttf'),('TimesVN-BoldItalic','Times New Roman Bold Italic.ttf')]:
 pdfmetrics.registerFont(TTFont(name,'/System/Library/Fonts/Supplemental/'+file))
pdfmetrics.registerFontFamily('TimesVN',normal='TimesVN',bold='TimesVN-Bold',italic='TimesVN-Italic',boldItalic='TimesVN-BoldItalic')
W,H=595.28,841.89;LEFT=85;RIGHT=57;TOP=74;BOTTOM=64;CW=W-LEFT-RIGHT
styles={
 'body':ParagraphStyle('body',fontName='TimesVN',fontSize=12.5,leading=15.7,alignment=TA_JUSTIFY,spaceAfter=8,allowWidows=0,allowOrphans=0),
 'h1':ParagraphStyle('h1',fontName='TimesVN-Bold',fontSize=13,leading=16,spaceAfter=8,keepWithNext=True),
 'h2':ParagraphStyle('h2',fontName='TimesVN-Bold',fontSize=12.5,leading=15.7,spaceBefore=5,spaceAfter=5,keepWithNext=True),
 'h3':ParagraphStyle('h3',fontName='TimesVN-BoldItalic',fontSize=12.5,leading=15.7,spaceBefore=4,spaceAfter=5,keepWithNext=True),
 'caption':ParagraphStyle('caption',fontName='TimesVN-Italic',fontSize=11.5,leading=14,alignment=TA_CENTER,spaceBefore=4,spaceAfter=9),
 'tablecap':ParagraphStyle('tablecap',fontName='TimesVN-Bold',fontSize=11.5,leading=14,spaceBefore=3,spaceAfter=6,keepWithNext=True),
 'cell':ParagraphStyle('cell',fontName='TimesVN',fontSize=10.5,leading=12.8,alignment=TA_LEFT),
 'headcell':ParagraphStyle('headcell',fontName='TimesVN-Bold',fontSize=10.5,leading=12.8,alignment=TA_LEFT),
 'formula':ParagraphStyle('formula',fontName='TimesVN-Italic',fontSize=12,leading=16,alignment=TA_CENTER,spaceBefore=3,spaceAfter=9),
 'bullet':ParagraphStyle('bullet',fontName='TimesVN',fontSize=12.5,leading=15.7,alignment=TA_JUSTIFY,leftIndent=10,firstLineIndent=-10,spaceAfter=7),
 'ref':ParagraphStyle('ref',fontName='TimesVN',fontSize=11.5,leading=14.5,spaceAfter=10,leftIndent=23,firstLineIndent=-23,splitLongWords=True),
}

def fmt(text):
 text=html.escape(text)
 text=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',text)
 text=re.sub(r'`([^`]+)`',r'\1',text)
 text=re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)',r'<i>\1</i>',text)
 # Allow line wrapping of long literal identifiers and URLs.
 text=text.replace('^α','<super>α</super>')
 return text

def draw_cover(canvas):
 # Match the sample cover's text positions and font sizes (points from page top).
 canvas.saveState()
 def line(text,top,size,font='TimesVN-Bold',x=None):
  canvas.setFont(font,size)
  baseline=H-top-(1000+pdfmetrics.getFont(font).face.descent)*size/1000
  if x is None:canvas.drawCentredString(311.64,baseline,text)
  else:canvas.drawString(x,baseline,text)
 line('ĐẠI HỌC PHENIKAA',75.55,14.05)
 line('TRƯỜNG CÔNG NGHỆ THÔNG TIN PHENIKAA',101.49,12.95)
 canvas.drawImage(str(A/'phenikaa_logo.png'),255.36,H-132.96-102.72,width=112.56,height=102.72)
 line('BÁO CÁO BÀI TẬP LỚN',260.94,18)
 line('NHÓM 3',291.54,18)
 line('MÔN: KHAI PHÁ DỮ LIỆU',317.55,15)
 line('DỰ ĐOÁN NHÓM VŨ KHÍ GÂY CHẾT TRONG PUBG',341.04,15.95)
 line('TỪ NGỮ CẢNH KHÔNG GIAN - THỜI GIAN',364.53,15.95)
 line('VÀ LỊCH SỬ HẠ GỤC',388.02,15.95)
 line('Giảng viên hướng dẫn: ThS. Phạm Kim Thành',432.01,12.5,'TimesVN',148.08)
 for top,text in zip([476.41,494.77,513.13],[
  '24100093 - Kiều Thị Thu Trang - 24100093@st.phenikaa-uni.edu.vn',
  '24100012 - Trần Minh Sang - 24100012@st.phenikaa-uni.edu.vn',
  '24102651 - Ngô Quang Thiện - 24102651@st.phenikaa-uni.edu.vn']):
  line(text,top,12.5,'TimesVN',148.08)
 label='Link Github dự án:  '
 line(label,650.65,12.5,'TimesVN-Italic',132.72)
 line('https://github.com/thyelmot/Project_PUBG',650.65,12.5,'TimesVN',
      132.72+pdfmetrics.stringWidth(label,'TimesVN-Italic',12.5))
 line('Hà Nội, tháng 10 năm 2026',751.32,12,'TimesVN')
 canvas.restoreState()

class Report(BaseDocTemplate):
 def __init__(self,path):
  super().__init__(str(path),pagesize=(W,H),leftMargin=LEFT,rightMargin=RIGHT,topMargin=TOP,bottomMargin=BOTTOM,title='Báo cáo bài tập lớn Khai phá dữ liệu - Dự đoán nhóm vũ khí PUBG',author='Nhóm 3 - Đại học Phenikaa')
  frame=Frame(LEFT,BOTTOM,CW,H-TOP-BOTTOM,id='normal',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
  self.addPageTemplates(PageTemplate(id='all',frames=[frame],onPageEnd=self.footer))
  self.content_start=0;self.entries=[]
 def beforeDocument(self):self.content_start=0;self.entries=[]
 def footer(self,c,d):
  if d.page==1:draw_cover(c)
  if self.content_start and d.page>=self.content_start:
   c.saveState();c.setFont('TimesVN',12);c.drawCentredString(W/2+14,37,str(d.page-self.content_start+1));c.restoreState()
 def afterFlowable(self,f):
  if getattr(f,'report_heading',False):
   if f.getPlainText().startswith('1. GIỚI THIỆU'):self.content_start=self.page
   key=f.bookmark;self.canv.bookmarkPage(key)
   self.canv.addOutlineEntry(f.getPlainText(),key,f.level,False)
   if f.level<=1:
    self.notify('TOCEntry',(f.level,f.getPlainText(),self.page-self.content_start+1,key))
   self.entries.append((f.getPlainText(),self.page,self.page-self.content_start+1))

# Reuse the university logo from the user-supplied cover.
with pdfplumber.open(ROOT/'report_mau.pdf') as p:
 p.pages[0].crop((255.36,132.96,367.92,235.68)).to_image(resolution=300).save(A/'phenikaa_logo.png')

story=[]
def center(t,size=14,bold=False,after=8):
 story.append(Paragraph(fmt(t),ParagraphStyle('cover',fontName='TimesVN-Bold' if bold else 'TimesVN',fontSize=size,leading=size*1.25,alignment=TA_CENTER,spaceAfter=after)))
story.extend([Spacer(1,1),PageBreak()])
center('MỤC LỤC',15,True,14)
toc=TableOfContents();toc.levelStyles=[ParagraphStyle('toc0',fontName='TimesVN-Bold',fontSize=11,leading=13,spaceBefore=3),ParagraphStyle('toc1',fontName='TimesVN',fontSize=10.5,leading=12,leftIndent=12,firstLineIndent=0,spaceBefore=1)]
toc.dotsMinLevel=0;story.append(toc);story.append(PageBreak())
lines=(ROOT/'bao_cao_khai_pha_du_lieu.md').read_text().splitlines();i=0;headcount=0;first=True;refs=False
while i<len(lines):
 line=lines[i].strip()
 if not line or line.startswith('<!--'):i+=1;continue
 if line.startswith('#'):
  level=len(line)-len(line.lstrip('#'))-1;title=line[level+2:];refs=title=='TÀI LIỆU THAM KHẢO' or refs
  if level==0 and not first:
   if title.startswith('PHỤ LỤC') or title in ('TÀI LIỆU THAM KHẢO','7. KẾT LUẬN'):story.append(PageBreak())
   else:story.append(Spacer(1,9))
  first=False;headcount+=1
  p=Paragraph(fmt(title),styles['h'+str(level+1)]);p.report_heading=True;p.level=level;p.bookmark='heading'+str(headcount);story.append(p);i+=1;continue
 if line.startswith('|'):
  rows=[]
  while i<len(lines) and lines[i].strip().startswith('|'):
   row=[x.strip() for x in lines[i].strip().strip('|').split('|')]
   if not all(re.match(r'^:?-+:?$',x) for x in row):rows.append(row)
   i+=1
  n=len(rows[0]);maxlens=[max(len(re.sub(r'`|\*','',r[j])) for r in rows) for j in range(n)]
  weights=[min(52,max(13,x)) for x in maxlens]
  widths=[CW*w/sum(weights) for w in weights]
  data=[[Paragraph(fmt(x),styles['headcell' if ri==0 else 'cell']) for x in row] for ri,row in enumerate(rows)]
  t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
  t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,-1),colors.white),('TEXTCOLOR',(0,0),(-1,-1),colors.black),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#777777')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
  t.spaceAfter=9;story.append(t);continue
 if line.startswith('!['):
  m=re.match(r'!\[(.*?)\]\((.*?)\)',line);from PIL import Image as PILImage
  path=ROOT/m.group(2);w,h=PILImage.open(path).size;scale=min(CW/w,285/h)
  im=Image(str(path),width=w*scale,height=h*scale)
  story.append(KeepTogether([im,Paragraph(fmt(m.group(1)),styles['caption'])]));i+=1;continue
 if line.startswith('> '):style='formula';line=line[2:]
 elif line.startswith('- '):style='bullet';line='- '+line[2:]
 elif line.startswith('**Bảng'):style='tablecap'
 elif refs:style='ref'
 else:style='body'
 story.append(Paragraph(fmt(line),styles[style]));i+=1
output=ROOT/'bao_cao_khai_pha_du_lieu.pdf';doc=Report(output);doc.multiBuild(story)
(A/'muc_luc.json').write_text(json.dumps(doc.entries,ensure_ascii=False,indent=2))
print(output)
with pdfplumber.open(output) as p:print('Pages:',len(p.pages),'Content starts:',doc.content_start)
