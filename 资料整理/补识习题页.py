import 教材提取 as M
import fitz,json,concurrent.futures,numpy as np
from pathlib import Path
from rapidocr_onnxruntime import RapidOCR
def scan(job):
 bid,p,n=job
 with fitz.open(p) as d:
  pix=d[n-1].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False);arr=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
  if not hasattr(M.LOCAL,'repair'):M.LOCAL.repair=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
  result,_=M.LOCAL.repair(arr,box_thresh=.25,text_score=.2)
  a=[dict(box=b,text=t,confidence=float(c)) for b,t,c in (result or [])]
  cache=M.OUT/bid/f'page-{n:04}.json';cache.with_suffix('.before.json').write_bytes(cache.read_bytes());cache.write_text(json.dumps(a,ensure_ascii=False),encoding='utf-8')
 print(bid,n,'补识',flush=True)
if __name__=='__main__':
 jobs=[];spec={}
 qs=json.loads((M.R/'题库/教材习题.json').read_text(encoding='utf-8'))
 plans=[b for f in M.OUT.glob('*计划.json') for b in json.loads(f.read_text(encoding='utf-8'))]
 for issue in json.loads((M.OUT/'题号疑点.json').read_text(encoding='utf-8')):
  b=next(b for b in plans if b['name']==issue['book']);c=next(c for c in b['chapters'] if c['chapter']==issue['chapter'])
  subset=[q for q in qs if q['book']==issue['book'] and q['chapter']==issue['chapter'] and q['type']==issue['type']]
  pages=set()
  for n in issue['missing_numbers']:
   before=[q for q in subset if int(q['original_number'].split('-')[-1])<n];after=[q for q in subset if int(q['original_number'].split('-')[-1])>n]
   lo=max(before,key=lambda q:int(q['original_number'].split('-')[-1]))['regions'][0]['pdf_page'] if before else c['start']+b['offset']
   hi=min(after,key=lambda q:int(q['original_number'].split('-')[-1]))['regions'][0]['pdf_page'] if after else c['end']+b['offset']
   pages.update(range(lo,hi+1))
  spec.setdefault(b['id'],set()).update(pages)
 for f in M.OUT.glob('*计划.json'):
  for b in json.loads(f.read_text(encoding='utf-8')):
   for n in spec.get(b['id'],[]):jobs.append((b['id'],b['file'],n))
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(scan,jobs))
