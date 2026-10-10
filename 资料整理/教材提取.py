from pathlib import Path
import sys,json,re,time,concurrent.futures,threading
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'工具依赖'))
import fitz,numpy as np
from rapidocr_onnxruntime import RapidOCR
LOCAL=threading.local()
OUT=R/'教材习题';OUT.mkdir(exist_ok=True)
def ocr_page(doc,n,scale=1.5):
 pix=doc[n].get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
 arr=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
 if not hasattr(LOCAL,'ocr'):LOCAL.ocr=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
 result,_=LOCAL.ocr(arr)
 return [{'box':b,'text':t,'confidence':float(c)} for b,t,c in (result or [])]
def setup():
 rows=[]
 for i,p in enumerate(sorted((R.parent/'教材').glob('*.pdf')),1):
  doc=fitz.open(p);bid=f'BK{i:02}';folder=OUT/bid;folder.mkdir(exist_ok=True)
  row=dict(id=bid,file=str(p),name=p.name,pages=len(doc),toc=doc.get_toc(),front=[])
  if len(doc)>1:
   def process(n):
    cache=folder/f'front-{n+1}.json'
    if not cache.exists():
     with fitz.open(p) as d:cache.write_text(json.dumps(ocr_page(d,n),ensure_ascii=False),encoding='utf-8')
    text='\n'.join(x['text'] for x in json.loads(cache.read_text(encoding='utf-8')))
    return dict(pdf_page=n+1,text=text)
   with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    row['front']=list(pool.map(process,range(min(20 if '答案' not in p.name else 4,len(doc)))))
   if '――' in p.name:
    text='\n'.join(f'===PDF页{n+1}===\n'+page.get_text() for n,page in enumerate(doc))
    (folder/'全文.txt').write_text(text,encoding='utf-8')
  rows.append(row);(OUT/'教材元数据.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
  print(bid,p.name,'前页已识别',flush=True)
if __name__=='__main__':setup()
