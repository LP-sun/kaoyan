from pathlib import Path
import json,re,sys,hashlib,concurrent.futures
import 教材提取 as M
import fitz
R=M.R;O=M.OUT
def run(plan):
 for book in plan:
  p=Path(book['file']);bid=book['id'];folder=O/bid;folder.mkdir(exist_ok=True)
  doc=fitz.open(p);off=book['offset'];jobs=sorted(set(n+off for c in book['chapters'] for n in range(c['start'],c['end']+1)))
  previous=folder/'习题.json';oldboxes={}
  if previous.exists():
   for q in json.loads(previous.read_text(encoding='utf-8')):
    for z in q['regions']:oldboxes[Path(z['image']).name]=z['bbox']
  def scan(n):
   cache=folder/f'page-{n:04}.json';img=folder/f'page-{n:04}.jpg'
   if not cache.exists():
    with fitz.open(p) as d:
     if book.get('use_text'):
      a=[]
      for block in d[n-1].get_text('dict')['blocks']:
       for line in block.get('lines',[]):
        t=''.join(s['text'] for s in line['spans']);x0,y0,x1,y1=line['bbox']
        a.append(dict(text=t,box=[[x0*1.5,y0*1.5],[x1*1.5,y0*1.5],[x1*1.5,y1*1.5],[x0*1.5,y1*1.5]],confidence=1.0))
     else:a=M.ocr_page(d,n-1,1.5)
     cache.write_text(json.dumps(a,ensure_ascii=False),encoding='utf-8')
   if not img.exists():
    with fitz.open(p) as d:d[n-1].get_pixmap(matrix=fitz.Matrix(1.7,1.7),alpha=False).save(img)
   return n
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
   for n in pool.map(scan,jobs):print(bid,'页',n,'已识别',flush=True)
  allq=[];chap=[]
  for c in book['chapters']:
   markers=[];kind='思考题' if isinstance(c['chapter'],int) else '习题';page_rows={}
   for pn in range(c['start']+off,c['end']+off+1):
    a=json.loads((folder/f'page-{pn:04}.json').read_text(encoding='utf-8'));a.sort(key=lambda x:(round(min(z[1] for z in x['box'])/15),min(z[0] for z in x['box'])));page_rows[pn]=a
    for ai,x in enumerate(a):
     t=x['text'].strip().lstrip('：:•●·.．');y=min(z[1] for z in x['box'])/1.5
     if y>doc[pn-1].rect.height*.12 and (re.fullmatch(r'习\s*题[.．·。]*',t) or (t=='习' and ai+1<len(a) and a[ai+1]['text'].strip()=='题')):kind='习题'
     match=re.match(r'^\*?\s*([ABCDabcd\d]{1,2})\s*[-－—–一～~]+\s*(\d(?:\s*\d){0,2})\s*(?:[.．、。:：]|(?=[\u4e00-\u9fffA-Za-z（(])|$)\s*(.*)',t)
     if match and str(match[1]).upper()==str(c['chapter']).upper():
      if not match[3].strip() and not re.search(r'[.．、。:：]$',t):continue
      markers.append(dict(pn=pn,y=y,number=f'{match[1]}-{int(re.sub(r"\s", "",match[2]))}',kind=kind,text=t,confidence=x['confidence']))
   if isinstance(c['chapter'],int):
    current='思考题';last=0
    for m in markers:
     number=int(m['number'].split('-')[-1])
     if number<=3 and last>=4:current='习题'
     m['kind']=current;last=number
   for i,m in enumerate(markers):
    end=markers[i+1] if i+1<len(markers) else dict(pn=c['end']+off,y=doc[c['end']+off-1].rect.height-15)
    regions=[];texts=[]
    for pn in range(m['pn'],end['pn']+1):
     page=doc[pn-1];y0=max(0,m['y']-8) if pn==m['pn'] else 20;y1=max(y0,end['y']-4) if pn==end['pn'] else page.rect.height-10
     if y1-y0<8:continue
     name=f'{bid}-C{c["chapter"]}-{m["kind"]}-{m["number"]}-p{pn}.jpg'
     box=[0,y0,page.rect.width,y1]
     if not (folder/name).exists() or oldboxes.get(name)!=box:page.get_pixmap(matrix=fitz.Matrix(1.7,1.7),clip=fitz.Rect(*box),alpha=False).save(folder/name)
     regions.append(dict(pdf_page=pn,book_page=pn-off,bbox=[0,y0,page.rect.width,y1],image=f'../教材习题/{bid}/{name}',full_page=f'../教材习题/{bid}/page-{pn:04}.jpg'))
     texts.extend(x['text'] for x in page_rows[pn] if y0<=min(z[1] for z in x['box'])/1.5<y1)
    q=dict(id=f'{bid}-{m["kind"]}-{m["number"]}',book=book['name'],chapter=c['chapter'],chapter_title=c.get('title',''),type=m['kind'],original_number=m['number'],question_ocr='\n'.join(texts),regions=regions,source_pdf=str(p.relative_to(R.parent)).replace('\\','/'),answer=None,status='OCR分题，题面以原图为准；边界待逐题复核')
    if any(z['id']==q['id'] for z in allq):q['id']+=f'-p{m["pn"]}'
    allq.append(q)
   chap.append(dict(chapter=c['chapter'],book_pages=[c['start'],c['end']],pdf_pages=[c['start']+off,c['end']+off],count=sum(q['chapter']==c['chapter'] for q in allq),markers=markers))
  (folder/'习题.json').write_text(json.dumps(allq,ensure_ascii=False,indent=2),encoding='utf-8')
  (folder/'分章审计.json').write_text(json.dumps(chap,ensure_ascii=False,indent=2),encoding='utf-8')
  print(bid,'提取',len(allq),'条',flush=True)
if __name__=='__main__':run(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
