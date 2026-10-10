from pathlib import Path
import json,csv,hashlib,urllib.parse
R=Path(__file__).resolve().parent;O=R/'教材习题';T=R/'题库'
allq=[];books=[];chapters=[];issues=[]
for f in sorted(O.glob('*计划.json')):
 for b in json.loads(f.read_text(encoding='utf-8')):
  if any(x['id']==b['id'] for x in books):continue
  books.append(b)
  qfile=O/b['id']/'习题.json'
  if qfile.exists():allq+=json.loads(qfile.read_text(encoding='utf-8'))
  for c in b['chapters']:
   ps=list(range(c['start']+b['offset'],c['end']+b['offset']+1))
   chapters.append(dict(book_id=b['id'],book=b['name'],chapter=c['chapter'],title=c.get('title',''),pages=[dict(pdf_page=n,book_page=n-b['offset'],image=f'../教材习题/{b["id"]}/page-{n:04}.jpg') for n in ps],source_pdf='../../'+str(Path(b['file']).relative_to(R.parent)).replace('\\','/')))
# 合并人工写作记录（写作/<教材ID>/<题目ID>.json）：按稳定 ID 附加，不改动原始提取记录。
WRITE=T/'写作';writing={}
if WRITE.exists():
 for wf in sorted(WRITE.rglob('*.json')):
  try:w=json.loads(wf.read_text(encoding='utf-8-sig'))
  except Exception as ex:issues.append(dict(book='writing',chapter=0,type='写作',missing_numbers=[],duplicate_numbers=[],status=f'写作文件解析失败：{wf.name}：{ex}'));continue
  wid=w.get('id') or wf.stem
  rec={'statement':w.get('statement',''),'subquestions':w.get('subquestions',[]),'figures':w.get('figures',[]),
       'syllabus_topics':w.get('syllabus_topics',[]),'solution':w.get('solution',{}),'review':w.get('review',{})}
  if wid in writing:issues.append(dict(book='writing',chapter=0,type='写作',missing_numbers=[],duplicate_numbers=[],status=f'写作记录重复 ID：{wid}'))
  writing[wid]=rec
for q in allq:
 if q['id'] in writing:q['writing']=writing[q['id']]
for b in books:
 for c in b['chapters']:
  for kind in ['思考题','习题']:
   qs=[q for q in allq if q['id'].startswith(b['id']+'-') and q['chapter']==c['chapter'] and q['type']==kind]
   ns=[int(q['original_number'].split('-')[-1]) for q in qs]
   if ns:
    missing=sorted(set(range(1,max(ns)+1))-set(ns));duplicates=sorted(n for n in set(ns) if ns.count(n)>1)
    if b['id']=='BK04' and c['chapter']==3 and kind=='思考题':missing=[n for n in missing if n!=22]
    if missing or duplicates:issues.append(dict(book=b['name'],chapter=c['chapter'],type=kind,missing_numbers=missing,duplicate_numbers=duplicates,status='待核对源页；不推造缺题'))
(T/'教材习题.json').write_text(json.dumps(allq,ensure_ascii=False,indent=2),encoding='utf-8')
(O/'题号疑点.json').write_text(json.dumps(issues,ensure_ascii=False,indent=2),encoding='utf-8')
with (T/'教材习题.csv').open('w',encoding='utf-8-sig',newline='') as f:
 keys=['id','book','chapter','type','original_number','question_ocr','source_pdf','status'];w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(allq)
data=dict(questions=allq,chapters=chapters,books=[dict(id=b['id'],name=b['name']) for b in books],issues=issues)
(T/'教材题库数据.js').write_text('const TEXTBOOK_DATA='+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+';',encoding='utf-8')
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>教材习题题库</title><style>body{font:16px/1.7 system-ui;background:#eef3f6;color:#182d40;margin:0}main{max-width:1050px;margin:auto;padding:24px}a{color:#17618c}article,.panel{background:white;border-radius:12px;padding:20px;margin:16px 0}input,select,button{font:inherit;padding:8px;margin:4px;border:1px solid #b6c5ce;border-radius:6px}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;background:#f3f6f8;padding:12px}small{color:#526779}textarea{width:95%;height:70px}.bar{position:sticky;top:0;background:#eef3f6;z-index:2;padding:8px}details{margin:10px 0}summary{cursor:pointer;color:#17618c}</style><main><h1>教材习题题库</h1><p>保留原题号、章节、PDF页与印刷页；公式及插图以原始页图为准。OCR分题边界待复核，完整章末页用于核查漏题和跨题插图。</p><p><a href="自动推荐刷题.html">自动推荐刷题</a> · <a href="物理考研题库.html">基础题与真题</a> · <a href="教材习题.json">结构化题库</a> · <a href="../教材习题/提取报告.md">提取范围与疑点</a></p><div class="bar"><select id="book"><option value="">全部教材</option></select><select id="chapter"><option value="">全部章节</option></select><select id="kind"><option value="">思考题与习题</option><option>思考题</option><option>习题</option></select><input id="search" placeholder="搜索题号 / OCR文字"><select id="mode"><option value="all">全部题目</option><option value="wrong">错题</option><option value="due">到期复测</option></select><button id="random">随机10题</button><button id="reset">恢复筛选结果</button><button id="export">导出学习记录</button></div><p id="stats"></p><details class="panel"><summary>完整章末习题页（按当前教材与章节筛选）</summary><p>这里保留提取范围内的每一页，不依赖OCR分题是否成功。原页含邻题。</p><div id="archive"></div></details><div id="list"></div><button id="prev">上一页</button><span id="page"></span><button id="next">下一页</button><h2>答案资料</h2><div id="answers"></div></main><script src="教材题库数据.js"></script><script>
const D=TEXTBOOK_DATA,$=s=>document.getElementById(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
/* 人工写作记录渲染：题面 + 可折叠解析；未接入时写作字段缺失，不影响原题库显示。 */
function writeBlock(w){if(!w)return '';
 const rev=w.review||{},sol=w.solution||{},st=rev.statement_status||'draft',cs=rev.solution_status||'not_started';
 const badge=t=>`<span style="display:inline-block;background:#e7f0f7;color:#17618c;border-radius:4px;padding:1px 6px;margin-right:6px;font-size:12px">${esc(t)}</span>`;
 const list=(arr,sep)=>Array.isArray(arr)&&arr.length?arr.map(x=>`<li>${esc(x)}</li>`).join(''):'';
 let h=`<div style="border-left:3px solid #17618c;padding:4px 10px;margin:8px 0">`;
 h+=`<p>${badge('题面 '+st)}${badge('解答 '+cs)}<small>人工记录</small></p>`;
 if(w.statement)h+=`<div>${esc(w.statement)}</div>`;
 if(Array.isArray(w.subquestions)&&w.subquestions.length)h+=`<ol>${list(w.subquestions)}</ol>`;
 if(Array.isArray(w.figures)&&w.figures.length)h+=`<ul>${w.figures.map(f=>`<li>${esc(typeof f==='string'?f:(f.caption||f.path||JSON.stringify(f)))}</li>`).join('')}</ul>`;
 if(Array.isArray(w.syllabus_topics)&&w.syllabus_topics.length)h+=`<p><small>大纲主题：${esc(w.syllabus_topics.join('、'))}</small></p>`;
 if(cs!=='not_started'||sol.final_answer||(sol.steps||[]).length){
  h+=`<details><summary>解析（${esc(cs)}；先做题后展开）</summary>`;
  if(sol.origin)h+=`<p><small>来源：${esc(sol.origin)}</small></p>`;
  if((sol.assumptions||[]).length)h+=`<p>适用条件/假设：</p><ul>${list(sol.assumptions)}</ul>`;
  if((sol.steps||[]).length)h+=`<ol>${list(sol.steps)}</ol>`;
  if(sol.final_answer)h+=`<p><strong>最终结果：</strong>${esc(sol.final_answer)}</p>`;
  if((sol.checks||[]).length)h+=`<p>检验：</p><ul>${list(sol.checks)}</ul>`;
  if((sol.common_errors||[]).length)h+=`<p>易错点：</p><ul>${list(sol.common_errors)}</ul>`;
  h+=`</details>`;
 }
 if((rev.issues||[]).length)h+=`<p><small>待解决疑点：${esc(rev.issues.join('；'))}</small></p>`;
 return h+`</div>`;
}
let records={};try{records=JSON.parse(localStorage.getItem('physics-records-v1')||'{}')}catch{}let page=0,randomIds=null;for(const b of D.books)$('book').add(new Option(b.name,b.id));function setChapters(){let value=$('chapter').value;$('chapter').innerHTML='<option value="">全部章节</option>';for(const n of [...new Set(D.chapters.filter(c=>!$('book').value||c.book_id===$('book').value).map(c=>String(c.chapter)))])$('chapter').add(new Option('章 / 附录 '+n,n));if([...$('chapter').options].some(o=>o.value===value))$('chapter').value=value}function selected(){return D.questions.filter(q=>(!$('book').value||q.id.startsWith($('book').value+'-'))&&(!$('chapter').value||String(q.chapter)===$('chapter').value)&&(!$('kind').value||q.type===$('kind').value)&&(!$('search').value||(q.id+' '+q.question_ocr).includes($('search').value))&&($('mode').value!=='wrong'||records[q.id]?.status==='wrong')&&($('mode').value!=='due'||records[q.id]?.due<=Date.now()))}function render(){let qs=selected();if(randomIds)qs=qs.filter(q=>randomIds.includes(q.id));let total=Math.max(1,Math.ceil(qs.length/15));page=Math.min(page,total-1);$('stats').textContent=`${D.questions.length} 条自动分题记录；当前筛选 ${qs.length} 条。完整章末页另行保留。`;$('page').textContent=` ${page+1} / ${total} `;$('list').innerHTML=qs.slice(page*15,page*15+15).map(q=>{let r=records[q.id]||{};return `<article><small>${esc(q.id)} · ${esc(q.book)} · 第${esc(q.chapter)}章 · ${esc(q.type)}</small><h3>原题 ${esc(q.original_number)}</h3><p>${esc(q.status)}</p>${q.regions.map(z=>`<details><summary>原页：印刷页${z.book_page} / PDF页${z.pdf_page}（保留完整插图，含邻题）</summary><img loading="lazy" src="${z.full_page}"></details><img loading="lazy" alt="题面自动裁图；插图不完整时展开原页" src="${z.image}">`).join('')}<details><summary>OCR文字（仅供搜索，不作为可靠公式转录）</summary><pre>${esc(q.question_ocr)}</pre></details>${writeBlock(q.writing)}<a href="../../${encodeURI(q.source_pdf)}#page=${q.regions[0]?.pdf_page||1}">打开教材来源</a><p><button data-id="${esc(q.id)}" data-ok="0">做错 / 不会</button><button data-id="${esc(q.id)}" data-ok="1">独立正确</button><small>${r.status==='wrong'?'待补课':r.status==='ok'?'已练习':'未练习'} ${r.due?'· 下次复测 '+new Date(r.due).toLocaleDateString():''}</small></p><textarea data-note="${esc(q.id)}" placeholder="错因 / 题面边界疑点">${esc(r.note||'')}</textarea><p>答案：${q.answer?'见已核验关联':'尚无逐题核验的答案关联，请按教材原题号核对答案资料。'}</p></article>`}).join('');$('archive').innerHTML=D.chapters.filter(c=>(!$('book').value||c.book_id===$('book').value)&&(!$('chapter').value||String(c.chapter)===$('chapter').value)).map(c=>`<details><summary>${esc(c.book)} · 章/附录 ${esc(c.chapter)} · ${c.pages.length}页</summary>${c.pages.map(p=>`<details><summary>印刷页${p.book_page} / PDF页${p.pdf_page}</summary><img loading="lazy" src="${p.image}"></details>`).join('')}</details>`).join('')}function save(){localStorage.setItem('physics-records-v1',JSON.stringify(records))}$('list').onclick=e=>{let id=e.target.dataset.id;if(!id)return;let ok=e.target.dataset.ok==='1',r=records[id]||{},now=Date.now();if(ok&&r.status==='ok'&&r.due>now){alert('尚未到延迟复测日期，不增加连续正确次数。');return}r.streak=ok?(r.streak||0)+1:0;r.status=ok?'ok':'wrong';r.last=now;r.due=now+(ok&&r.streak>=2?14:3)*86400000;records[id]=r;save();render()};$('list').onchange=e=>{let id=e.target.dataset.note;if(id){records[id]={...(records[id]||{}),note:e.target.value};save()}};for(const id of ['book','chapter','kind','search','mode'])$(id).oninput=()=>{if(id==='book')setChapters();page=0;randomIds=null;render()};$('random').onclick=()=>{let a=selected();for(let i=a.length-1;i>0;i--){let j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}randomIds=a.slice(0,10).map(q=>q.id);page=0;render()};$('reset').onclick=()=>{randomIds=null;page=0;render()};$('prev').onclick=()=>{page=Math.max(0,page-1);render();window.scrollTo(0,0)};$('next').onclick=()=>{page++;render();window.scrollTo(0,0)};$('export').onclick=()=>{let u=URL.createObjectURL(new Blob([JSON.stringify(records,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=u;a.download='物理题库学习记录.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};setChapters();render();
</script></html>'''
answers=[]
for b in books:
 page={'BK01':406,'BK04':476,'BK05':506,'BK06':462,'BK07':322}.get(b['id'])
 if page:
  source=urllib.parse.quote(str(Path(b['file']).relative_to(R.parent)).replace('\\','/'))
  answers.append(f'<p><a href="../../{source}#page={page}">{b["name"]}：教材自带习题答案</a> · PDF第{page}页起，按原题号人工核对。</p>')
for p in sorted((R.parent/'教材').glob('*答案*.pdf')):answers.append(f'<p><a href="../../教材/{urllib.parse.quote(p.name)}">{p.name}</a> · 整份参考资料；未自动配对。电磁学为第三版答案，与第二版教材需核题。</p>')
html=html.replace('<div id="answers"></div>','<div id="answers">'+''.join(answers)+'</div>')
(T/'教材习题题库.html').write_text(html,encoding='utf-8')
base=T/'物理考研题库.html';s=base.read_text(encoding='utf-8')
if '教材习题题库.html' not in s:s=s.replace('<h1>普通物理 · 量子力学题库</h1>','<h1>普通物理 · 量子力学题库</h1><p><a href="教材习题题库.html">进入教材全书思考题与习题题库</a></p>');base.write_text(s,encoding='utf-8')
report=['# 教材习题提取报告',f'已建立 {len(allq)} 条自动分题记录，覆盖 {len(books)} 个教材版本的目录指定章末及附录习题范围。完整页归档用于保留OCR漏识题号、插图及跨页内容。自动分题不等于逐题人工校对完成。','参考实现：https://github.com/luoluohi/fundamentals-of-circuit-analysis-exercise-solutions','|教材版本|分题记录|章/附录范围|完整页数|','|---|---:|---:|---:|']
for b in books:report.append(f'|{b["name"]}|{sum(q["id"].startswith(b["id"]+"-") for q in allq)}|{len(b["chapters"])}|{sum(len(c["pages"]) for c in chapters if c["book_id"]==b["id"])}|')
report+=['\n## 题号疑点',f'{len(issues)} 组存在题号断号或重复，见题号疑点.json；未虚构填补题面。请使用完整章末原页核对。','\n## 答案与排除','仅提取和整理题面，不生成整套推导答案。教材自带答案和独立答案文件保留原文入口；电磁学答案第三版不与第二版直接匹配。量子力学教程.pdf为单页DRM提示文件，排除。','\n## 字段与复现','每题保存教材版本、原题号、类别、章节、PDF页/印刷页、裁图坐标、完整原页、OCR文字和复核状态。修改计划后可复用缓存重新提取；构建教材题库.py生成离线页面和JSON/CSV。原教材不修改。']
report+=['\n## 已核实的原书跳号','力学第二版第3章思考题在印刷页146（PDF页166）从3-21直接跳到3-23；原扫描页没有3-22。保持原题号，不补造题面。此处已人工查看整页确认，未计为OCR缺题。','\n## 范围说明','提取目录列出的全部章末思考题、习题以及附录习题；正文例题及仅引用题号的句子不作为独立习题重复入库。两册答案资料保留整份入口，未将其中重复题面重复计数。两个量子物理版本单独计数，不作跨版本去重。']
(O/'提取报告.md').write_text('\n'.join(report),encoding='utf-8')
manifest=[]
for p in sorted((R.parent/'教材').glob('*.pdf')):
 manifest.append(dict(file=str(p.relative_to(R.parent)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),role='排除：单页DRM提示' if p.name=='量子力学教程.pdf' else '答案整份参考' if '答案' in p.name else '教材习题来源'))
(O/'来源清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(len(allq),'分题记录；',len(chapters),'章附录；',len(issues),'疑点组')
