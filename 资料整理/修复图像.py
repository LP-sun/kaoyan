import 教材提取 as M
import fitz,json
from pathlib import Path
plans=[b for f in M.OUT.glob('*计划.json') for b in json.loads(f.read_text(encoding='utf-8'))]
for b in plans:
 folder=M.OUT/b['id']
 with fitz.open(b['file']) as d:
  for p in folder.glob('page-*.jpg'):
   if p.stat().st_size<100:
    n=int(p.stem.split('-')[-1]);d[n-1].get_pixmap(matrix=fitz.Matrix(1.7,1.7),alpha=False).save(p);print('修复',p.name,flush=True)
