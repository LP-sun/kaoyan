from pathlib import Path
import json,re
R=Path(__file__).resolve().parent/'教材习题'
for d in sorted(R.glob('BK*')):
 print('\n'+d.name)
 for f in sorted(d.glob('front-*.json'),key=lambda f:int(f.stem.split('-')[-1])):
  a=json.loads(f.read_text(encoding='utf-8'))
  for x in a:
   text=x['text'];y=sum(p[1] for p in x['box'])/4
   if re.search('思考题|^习题|^第[一二三四五六七八九十]+章|^附录',text):
    near=[z['text'] for z in a if abs(sum(p[1] for p in z['box'])/4-y)<20 and z['box'][0][0]>x['box'][1][0]]
    print(f.stem,text,' '.join(near))
