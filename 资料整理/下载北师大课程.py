import urllib.request,urllib.parse,json,hashlib
from html.parser import HTMLParser
from pathlib import Path
from pypdf import PdfReader
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
base='https://physicsfaculty.bnu.edu.cn/Public/web/application/faculty/guowenan/QM/index.html'
class P(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,t,a):
  if t=='a':
   u=dict(a).get('href','')
   if u.endswith('.pdf'):self.links.append(urllib.parse.urljoin(base,u))
with op.open(base,timeout=20) as r:s=r.read().decode('utf-8','replace')
p=P();p.feed(s);urls=[u for u in p.links if '/homework2020/' in u or u.endswith('/main.pdf')]
records=[];folder=Path('资料整理/教程/北师大量子力学');folder.mkdir(exist_ok=True)
for u in urls:
 dest=folder/Path(urllib.parse.urlparse(u).path).name
 try:
  with op.open(u,timeout=15) as r:raw=r.read()
  tmp=dest.with_suffix('.tmp');tmp.write_bytes(raw);d=PdfReader(tmp);tmp.replace(dest)
  rec=dict(file=str(dest),url=u,pages=len(d.pages),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),status='已下载普通PDF');print(dest.name,len(d.pages),flush=True)
 except Exception as e:rec=dict(file=str(dest),url=u,status='失败',error=str(e));print(dest.name,str(e),flush=True)
 records.append(rec)
Path('资料整理/教程/北师大下载记录.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
