import urllib.request
from pathlib import Path
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
url='https://library.shanghaitech.edu.cn/dzts/list.htm'
try:
 with op.open(url,timeout=20) as r:
  data=r.read();print(r.status,r.url);Path('资料整理/图书馆电子图书入口.html').write_bytes(data)
 from bs4 import BeautifulSoup
 soup=BeautifulSoup(data,'html.parser')
 for a in soup.select('a[href]'):
  name=a.get_text(' ',strip=True)
  if any(k in name for k in ['超星','读秀','科学','图书','发现','馆藏','数据库']):print(name,a.get('href'))
except Exception as e:print(type(e).__name__,str(e))
