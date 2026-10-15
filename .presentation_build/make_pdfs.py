import json,pathlib,html
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Image,KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pypdfium2 as pdfium
from pypdf import PdfReader
root=pathlib.Path(__file__).resolve().parents[1]
build=root/'.presentation_build'; out=root/'Project_Presentation_Output'
data=json.loads((build/'content.json').read_text(encoding='utf-8'))
pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialBold','C:/Windows/Fonts/arialbd.ttf'))
styles={
'title':ParagraphStyle('title',fontName='ArialBold',fontSize=24,leading=29,textColor=HexColor('#112B3C'),spaceAfter=16),
'head':ParagraphStyle('head',fontName='ArialBold',fontSize=13,leading=18,textColor=HexColor('#007F7B'),spaceAfter=8),
'body':ParagraphStyle('body',fontName='Arial',fontSize=11,leading=16,textColor=HexColor('#112B3C'),spaceAfter=10),
'source':ParagraphStyle('source',fontName='Arial',fontSize=8,leading=12,textColor=HexColor('#526775'),spaceAfter=8)}
def para(t,k='body'):return Paragraph(html.escape(t).replace('\n','<br/>'),styles[k])
def footer(c,d):
 c.setFont('Arial',8);c.setFillColor(HexColor('#526775'));c.drawString(44,28,'Decentralized Role-Leasing IoT Protocol');c.drawRightString(550,28,str(d.page))
story=[]
for i,s in enumerate(data['slides']):
 story+=[para(f"Slide {i+1:02d}  |  "+s['title'].replace('\n',' '),'title')]
 preview=build/'renders'/f'slide-{i+1:02d}.png'
 if preview.exists():story+=[Image(str(preview),width=504,height=283.5),Spacer(1,15)]
 story+=[para('Speaking guide','head')]
 # Split notes into digestible paragraphs, preserving all technical detail.
 n=s['notes']; sentences=n.split('. ');cut=max(1,len(sentences)//2)
 story+=[para('. '.join(sentences[:cut])+('.' if cut<len(sentences) else '')),para('. '.join(sentences[cut:]))]
 story+=[para('Implementation evidence: '+s['source'],'source')]
 story+=[para('Panel prompt: Explain the tradeoff and implementation boundary on this slide.','source')]
 if i<len(data['slides'])-1:story.append(PageBreak())
SimpleDocTemplate(str(out/'Project_Presentation_Speaker_Notes.pdf'),pagesize=(595,842),rightMargin=44,leftMargin=44,topMargin=42,bottomMargin=44).build(story,onFirstPage=footer,onLaterPages=footer)
story=[para('Project viva preparation','title'),para('24 questions grounded in the supplied implementation','head'),para('Use the code references to support each answer. The system is a local simulator. Role availability, normalized energy, and subnet sensor delivery must be explained within their modeled boundaries.'),para('Environment note: Mesa 3.5.1 conflicts with runner.py assigning model.scenario. Verification uses Mesa 3.3.1. Pin a compatible release and include SciPy for the study analyzer.')]
for i,(q,a,src) in enumerate(data['viva']):
 story.append(KeepTogether([para(f'{i+1:02d}. {q}','head'),para(a),para('Evidence: '+src,'source'),Spacer(1,9)]))
SimpleDocTemplate(str(out/'Project_Viva_Questions.pdf'),pagesize=(595,842),rightMargin=44,leftMargin=44,topMargin=42,bottomMargin=44).build(story,onFirstPage=footer,onLaterPages=footer)
for name in ['Project_Presentation_Speaker_Notes','Project_Viva_Questions']:
 file=out/(name+'.pdf'); doc=pdfium.PdfDocument(str(file)); rd=PdfReader(str(file))
 assert len(rd.pages)>0 and all(page.extract_text().strip() for page in rd.pages)
 dest=build/name;dest.mkdir(exist_ok=True)
 for i,page in enumerate(doc):page.render(scale=1).to_pil().save(dest/f'page-{i+1:02d}.png')
 print(name,len(doc),'pages, rendered and text checked')

