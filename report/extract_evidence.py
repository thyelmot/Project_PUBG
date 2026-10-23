"""Extract saved notebook displays; never execute research cells."""
from pathlib import Path
import json, base64, hashlib, re
from io import StringIO
import pandas as pd
import fitz

ROOT=Path(__file__).resolve().parent
(ROOT/'figures').mkdir(exist_ok=True)
(ROOT/'evidence').mkdir(exist_ok=True)
index=[]
for path in sorted((ROOT.parent/'output').glob('*.ipynb')):
    nb=json.loads(path.read_text(encoding='utf-8'))
    label='display'
    for ci,cell in enumerate(nb['cells']):
        for oi,out in enumerate(cell.get('outputs',[])):
            data=out.get('data',{})
            txt=''.join(out.get('text',[]))
            if txt.strip() and len(txt.strip())<100:
                label=txt.strip().removesuffix('.csv')
            stem=f'{path.stem}_{ci}_{oi}'
            record={'notebook':path.name,'cell':ci,'output':oi,'label':label}
            if 'text/html' in data:
                html=''.join(data['text/html'])
                if '<table' in html:
                    frames=pd.read_html(StringIO(html))
                    if not frames:continue
                    frame=frames[0]
                    frame.to_csv(ROOT/'evidence'/f'{stem}.csv',index=False)
                    record.update(table=f'evidence/{stem}.csv',columns=list(map(str,frame.columns)),rows=len(frame))
                    index.append(record)
            if 'image/png' in data:
                raw=base64.b64decode(''.join(data['image/png']))
                (ROOT/'figures'/f'{stem}.png').write_bytes(raw)
                record.update(figure=f'figures/{stem}.png',sha256=hashlib.sha256(raw).hexdigest())
                index.append(record)
    (ROOT/'evidence'/f'{path.stem}.txt').write_text('\n'.join(''.join(o.get('text',o.get('data',{}).get('text/plain',[]))) for c in nb['cells'] for o in c.get('outputs',[])),encoding='utf-8')
(ROOT/'evidence/index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
doc=fitz.open(ROOT.parent/'BaoCaoBTL_ML.pdf')
(ROOT/'evidence/reference.txt').write_text('\n'.join(p.get_text() for p in doc),encoding='utf-8')
doc[0].get_pixmap(matrix=fitz.Matrix(1,1)).save(ROOT/'evidence/reference_cover.png')
print('Extracted',len(index),'displays')
for r in index:
    if r['notebook'].endswith('S12.ipynb') and r['cell']==43:print(r)
