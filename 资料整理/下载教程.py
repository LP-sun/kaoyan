import urllib.request,json,hashlib
from pathlib import Path
from pypdf import PdfReader
urls=[('OpenStax大学物理1.pdf','https://assets.openstax.org/oscms-prodcms/media/documents/University_Physics_Volume_1_-_WEB.pdf'),('Tong量子力学.pdf','https://www.damtp.cam.ac.uk/user/tong/qm/qm.pdf'),('Tong电磁学.pdf','https://www.damtp.cam.ac.uk/user/tong/em/electromagnetism.pdf'),('Tong统计物理.pdf','https://www.damtp.cam.ac.uk/user/tong/statphys/statphys.pdf')]
records=[]
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for name,url in urls:
 p=Path('资料整理/教程')/name
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
  with op.open(req,timeout=25) as r:p.write_bytes(r.read())
  d=PdfReader(p);rec=dict(file=str(p),url=url,pages=len(d.pages),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),status='已下载并验证PDF')
 except Exception as e:
  rec=dict(file=str(p),url=url,status='下载失败',error=str(e));None
 records.append(rec);print(json.dumps(rec,ensure_ascii=False),flush=True)
Path('资料整理/教程/下载记录.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')


