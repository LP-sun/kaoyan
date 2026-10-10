from pathlib import Path
import json
from PIL import Image,ImageDraw
R=Path(__file__).resolve().parent;T=R/'题库';O=R/'教材习题'
qs=json.loads((T/'教材习题.json').read_text(encoding='utf-8'))
assert len({q['id'] for q in qs})==len(qs)
pages=set();cross=0
for q in qs:
 assert (R.parent/q['source_pdf']).exists()
 assert q['regions'],q['id']
 if len(q['regions'])>1:cross+=1
 for z in q['regions']:
  assert 0<=z['bbox'][0]<z['bbox'][2] and 0<=z['bbox'][1]<z['bbox'][3]
  for key in ['image','full_page']:
   p=(T/z[key]).resolve();assert p.exists(),p
   with Image.open(p) as im:assert im.width>0 and im.height>0
  pages.add((q['book'],z['pdf_page']))
archive=0
for f in O.glob('*计划.json'):
 for b in json.loads(f.read_text(encoding='utf-8')):
  for c in b['chapters']:
   for pn in range(c['start']+b['offset'],c['end']+b['offset']+1):
    assert (O/b['id']/f'page-{pn:04}.jpg').exists(),(b['id'],pn)
    archive+=1
canvas=Image.new('RGB',(1500,1900),'white');draw=ImageDraw.Draw(canvas)
sample=[]
for b in sorted(set(q['book'] for q in qs)):
 a=[q for q in qs if q['book']==b];sample.extend([a[0],a[len(a)//2],a[-1]])
for i,q in enumerate(sample):
 p=T/q['regions'][0]['image'];im=Image.open(p).convert('RGB');im.thumbnail((475,275));x=(i%3)*500;y=(i//3)*310;canvas.paste(im,(x,y+25));draw.text((x+5,y+4),q['id'],fill='black')
canvas.save(O/'题面裁图抽查.jpg')
report=dict(question_records=len(qs),archive_pages=archive,cross_page_records=cross,unique_ids=True,all_source_and_image_paths_valid=True,all_images_nonempty=True,pending_number_groups=len(json.loads((O/'题号疑点.json').read_text(encoding='utf-8'))))
(O/'验证结果.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
