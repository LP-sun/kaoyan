from pathlib import Path
import urllib.request,json,hashlib
from pypdf import PdfReader
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
items=[('Tong动力学与相对论.pdf','https://www.damtp.cam.ac.uk/user/tong/relativity/dynrel.pdf'),('清华陈曦光学讲义.pdf','https://ithatron.phys.tsinghua.edu.cn/downloads/optics.pdf')]
rec=[]
for name,u in items:
 p=Path('资料整理/教程')/name
 try:
  with op.open(u,timeout=25) as r:raw=r.read()
  temp=p.with_suffix('.tmp');temp.write_bytes(raw);d=PdfReader(temp);temp.replace(p);rec.append(dict(file=str(p),url=u,pages=len(d.pages),sha256=hashlib.sha256(raw).hexdigest(),status='已下载普通PDF'));print(name,len(d.pages),flush=True)
 except Exception as e:rec.append(dict(file=str(p),url=u,status='失败',error=str(e)));print(name,str(e),flush=True)
Path('资料整理/教程/力学光学下载记录.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2),encoding='utf-8')
