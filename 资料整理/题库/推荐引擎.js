/* 可在浏览器和 Node 中使用；读取练习进度，不自动改写进度。 */
function recommendPractice(questions, analyses, records, options={}) {
  const exam=options.exam||'651', now=options.now??Date.now(), budget=Number(options.minutes)||60;
  const byId=new Map(questions.map(q=>[q.id,q]));
  const eligible=analyses.filter(a=>a.exams[exam]&&['大纲候选','概念了解','已核验核心','已核验相关'].includes(a.exams[exam].tier)&&!a.dependency_warning&&(options.includeOld||a.book_id!=='BK08')&&byId.has(a.id));
  const topics=new Map();
  for(const a of eligible)for(const e of a.exams[exam].evidence){let s=topics.get(e.topic)||{done:0,total:0};s.total++;if(records[a.id]?.status==='ok')s.done++;topics.set(e.topic,s)}
  const candidates=eligible.map(a=>{
    const r=records[a.id]||{},e=a.exams[exam],due=Number.isFinite(r.due)&&r.due<=now;
    // 未到期的已练题退出；错题先补课，避免同一天反复重刷。
    if(r.status&&Number.isFinite(r.due)&&!due)return null;
    if(r.status==='ok'&&!due)return null;
    const weakness=e.evidence.length?Math.max(...e.evidence.map(h=>{const t=topics.get(h.topic);return 1-t.done/t.total})):0;
    let score=due?100:20;const reasons=[];
    if(due){score+=Math.min(15,Math.floor((now-r.due)/86400000));reasons.push('已到期复测')}
    if(r.status==='wrong'){score+=25;reasons.push('上次做错，先补知识再闭卷检验')}
    score+=20*weakness;reasons.push('补充主题练习覆盖');
    if(e.tier==='概念了解'){score-=12;reasons.push('大纲仅要求了解，限制练习深度')}
    if(a.type==='思考题')score+=3;
    if(e.confidence==='低')score-=15;
    return {analysis:a,question:byId.get(a.id),score,reasons,lane:due?'复测':'新题'};
  }).filter(Boolean).sort((a,b)=>b.score-a.score||a.analysis.id.localeCompare(b.analysis.id,'zh-CN',{numeric:true}));
  const selected=[],themeCount=new Map(),groupCount=new Map();let used=0,concept=0;
  for(const c of candidates){
    const a=c.analysis,topic=a.exams[exam].evidence[0]?.topic||a.id,group=a.book_id+':'+a.chapter,minutes=Math.max(1,Number(a.estimated_minutes)||15);
    if(used+minutes>budget)continue;
    if(c.lane==='新题'&&((themeCount.get(topic)||0)>=2||(groupCount.get(group)||0)>=3))continue;
    if(a.exams[exam].tier==='概念了解'&&concept>=1)continue;
    selected.push({...c,minutes});used+=minutes;themeCount.set(topic,(themeCount.get(topic)||0)+1);groupCount.set(group,(groupCount.get(group)||0)+1);if(a.exams[exam].tier==='概念了解')concept++;
  }
  return {selected,estimatedMinutes:used,eligible:eligible.length,candidates:candidates.length};
}
if(typeof module!=='undefined')module.exports={recommendPractice};
