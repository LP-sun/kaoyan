import 教材提取 as M
from pathlib import Path
import json,fitz
p=next((M.R.parent/'教材').glob('*――*'))
with fitz.open(p) as d:
 for n in [91,92,454]:
  a=M.ocr_page(d,n-1)
  (M.OUT/'BK08'/f'page-{n:04}.json').write_text(json.dumps(a,ensure_ascii=False),encoding='utf-8')
  print(n,'重新OCR',flush=True)
