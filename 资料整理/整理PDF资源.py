from pathlib import Path
import urllib.request,json,hashlib,shutil,logging
from pypdf import PdfReader
logging.getLogger('pypdf').setLevel(logging.ERROR)
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
items=[('Tong电磁学.pdf','https://www.damtp.cam.ac.uk/user/tong/em/em.pdf')]
record=[]
for name,u in items:
 p=Path('资料整理/教程')/name
 try:
  with op.open(u,timeout=25) as r:raw=r.read()
  tmp=p.with_suffix('.tmp');tmp.write_bytes(raw);d=PdfReader(tmp);tmp.replace(p)
  record.append(dict(file=str(p),url=u,pages=len(d.pages),status='已下载普通PDF',sha256=hashlib.sha256(raw).hexdigest()));print(name,len(d.pages))
 except Exception as e:record.append(dict(file=str(p),url=u,status='失败',error=str(e)));print(e)
Path('资料整理/教程/补充下载记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
local=json.loads(Path('资料整理/本地材料索引.json').read_text(encoding='utf-8'))
seen=set();selected=[]
for r in local:
 p=Path(r['path']);name=p.name
 if not ('朗道' in name or '数学物理' in name or str(p).find('统计物理2026')>=0):continue
 sha=hashlib.sha256(p.read_bytes()).hexdigest()
 if sha in seen:continue
 seen.add(sha);dest=Path('资料整理/教程/本地补充')/name;dest.parent.mkdir(exist_ok=True);shutil.copy2(p,dest)
 selected.append(dict(source=str(p),file=str(dest),sha256=sha,pages=len(PdfReader(dest).pages),role='大纲辅助，非指定教材'))
Path('资料整理/教程/本地补充记录.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8');print('本地补充',len(selected))
