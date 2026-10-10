import 教材提取 as M
import fitz,json,re,numpy as np,concurrent.futures
from pathlib import Path
plans=[b for f in M.OUT.glob('*计划.json') for b in json.loads(f.read_text(encoding='utf-8'))]
qs=json.loads((M.R/'题库/教材习题.json').read_text(encoding='utf-8'))
jobs={}
for issue in json.loads((M.OUT/'题号疑点.json').read_text(encoding='utf-8')):
 b=next(b for b in plans if b['name']==issue['book']);c=next(c for c in b['chapters'] if c['chapter']==issue['chapter'])
 subset=[q for q in qs if q['book']==issue['book'] and q['chapter']==issue['chapter'] and q['type']==issue['type']]
 for n in issue['missing_numbers']:
  before=[q for q in subset if int(q['original_number'].split('-')[-1])<n];after=[q for q in subset if int(q['original_number'].split('-')[-1])>n]
  lo=max(before,key=lambda q:int(q['original_number'].split('-')[-1]))['regions'][0]['pdf_page'] if before else c['start']+b['offset'];hi=min(after,key=lambda q:int(q['original_number'].split('-')[-1]))['regions'][0]['pdf_page'] if after else c['end']+b['offset']
  for pn in range(lo,hi+1):jobs.setdefault((b['id'],pn),dict(book=b,targets=set()))['targets'].add(f'{c["chapter"]}-{n}')
def scan(job):
 (bid,pn),spec=job;b=spec['book'];cache=M.OUT/bid/f'page-{pn:04}.json';a=json.loads(cache.read_text(encoding='utf-8'))
 with fitz.open(b['file']) as d:
  page=d[pn-1];clip=fitz.Rect(page.rect.width*.06,0,page.rect.width*.43,page.rect.height);pix=page.get_pixmap(matrix=fitz.Matrix(2,2),clip=clip,alpha=False)
  if not hasattr(M.LOCAL,'number'):M.LOCAL.number=M.RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
  arr=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3);result,_=M.LOCAL.number(arr,box_thresh=.25,text_score=.2)
  found=[]
  for box,t,score in result or []:
   m=re.match(r'^\s*([ABCDabcd\d]{1,2})\s*[-－—–一～~]+\s*(\d(?:\s*\d){0,2})\s*[.．、。:：]?',t)
   if not m:continue
   number=f'{m[1]}-{int(re.sub(r"\s","",m[2]))}'
   if number not in spec['targets']:continue
   y=min(z[1] for z in box)/2;found.append((number,y,t))
   bbox=[[ (z[0]/2+clip.x0)*1.5,z[1]/2*1.5] for z in box]
   candidates=[x for x in a if abs(min(z[1] for z in x['box'])/1.5-y)<8 and x['box'][0][0]/1.5<page.rect.width*.5]
   if candidates:
    x=min(candidates,key=lambda x:x['box'][0][0]);x['text']=number+'. '+re.sub(r'^\s*.*?[-－—–一～~]+\s*\d+\s*[.．、。:：]?','',x['text']) if re.match(r'^\s*\d\s*[-－—–一～~]',x['text']) else number+'. '+x['text']
   else:a.append(dict(text=number+'. '+t[m.end():],box=bbox,confidence=float(score),number_recovered=True))
 cache.write_text(json.dumps(a,ensure_ascii=False),encoding='utf-8');print(bid,pn,found,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(scan,jobs.items()))
