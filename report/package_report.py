from pathlib import Path
import hashlib,json,zipfile,shutil
import fitz
from PIL import Image,ImageDraw
R=Path(__file__).resolve().parent
d=fitz.open(R/'main.pdf')
tiles=[]
for p in d:
    pix=p.get_pixmap(matrix=fitz.Matrix(.4,.4),alpha=False)
    tiles.append(Image.frombytes('RGB',[pix.width,pix.height],pix.samples))
out=Image.new('RGB',(5*250,((len(tiles)+4)//5)*360),'#aaaaaa')
draw=ImageDraw.Draw(out)
for i,im in enumerate(tiles):
    out.paste(im,((i%5)*250,(i//5)*360))
    draw.text(((i%5)*250,(i//5)*360+338),str(i+1),fill='black')
out.save(R/'evidence/contact_final.png')
for i in (0,12,13,len(d)-1):d[i].get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(R/'evidence'/f'qa_{i+1}.png')
inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (R.parent/'output').glob('*.ipynb')}
(R/'evidence/input_hashes.json').write_text(json.dumps(inputs,indent=2),encoding='utf8')
shutil.copyfile(R/'main.pdf',R/'BaoCao_KhaiPhaDuLieu_PUBG.pdf')
with zipfile.ZipFile(R/'BaoCao_KhaiPhaDuLieu_PUBG_LaTeX.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(R.rglob('*')):
        if not p.is_file() or p.suffix in {'.zip','.aux','.log','.out','.toc'} or p.name=='main.pdf':continue
        if p.parent.name=='evidence' and (p.name.startswith(('qa_','contact','reference','before_'))):continue
        z.write(p,p.relative_to(R))
print('PDF pages:',len(d),'ZIP CRC:',zipfile.ZipFile(R/'BaoCao_KhaiPhaDuLieu_PUBG_LaTeX.zip').testzip())
