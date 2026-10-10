/* 纯函数；掌握指标为学习策略估计，不是命题预测。兼容旧版练习记录。 */
const DAY=86400000;
function practiceEvents(r={}) {
 const h=(r.history||[]).filter(x=>Number.isFinite(x.at)&&['ok','wrong','assisted'].includes(x.outcome));
 if(['ok','wrong','assisted'].includes(r.status)&&Number.isFinite(r.last)&&!h.some(x=>x.at===r.last))h.push({at:r.last,outcome:r.status,legacy:true});
 return h.sort((a,b)=>a.at-b.at);
}
function recordPractice(r={},outcome,o={}) {
 if(!['ok','wrong','assisted'].includes(outcome))throw Error('无效结果');
 const now=o.now??Date.now(),h=practiceEvents(r),last=h.at(-1),delayed=outcome==='ok'&&!!last&&now-last.at>=DAY&&(!Number.isFinite(r.due)||now>=r.due);
 const streak=outcome==='ok'?(last?.outcome==='ok'?(r.streak||1)+(delayed?1:0):1):0;
 const interval=outcome==='ok'?(streak>=3?30:streak>=2?14:3):outcome==='assisted'?2:3;
 return {...r,status:outcome,last:now,due:now+interval*DAY,streak,history:[...h,{at:now,outcome,delayed,minutes:Number(o.minutes)>0?Number(o.minutes):null,error:o.error||''}]};
}
function recommendPractice(questions,analyses,records,options={}) {
 const exam=options.exam||'651',now=options.now??Date.now(),budget=Math.max(0,Number(options.minutes??60)),mode=options.mode||'balanced',byId=new Map(questions.map(q=>[q.id,q]));
 const REL_RANK={'high':3,'medium':2,'low':1,'none':0};
 const relOk=a=>{if(!options.minRelevance)return true;const lv=a.relevance&&a.relevance.level;return lv!=null&&REL_RANK[lv]>=REL_RANK[options.minRelevance]};
 const eligible=analyses.filter(a=>byId.has(a.id)&&['大纲候选','概念了解','已核验核心','已核验相关'].includes(a.exams?.[exam]?.tier)&&!a.dependency_warning&&!records[a.id]?.blocked&&(options.includeOld||a.book_id!=='BK08')&&(!options.focus||a.exams[exam].evidence.some(e=>e.topic===options.focus))&&relOk(a));
 const topics=new Map(),weakErrors=new Set(),times={};
 for(const a of eligible){
  const h=practiceEvents(records[a.id]),daily=new Map();for(const x of h){daily.set(Math.floor(x.at/DAY),x);if(x.outcome==='ok'&&x.minutes>0&&x.minutes<=180)(times[a.type]??=[]).push(x.minutes)}
  for(const e of a.exams[exam].evidence){
   const s=topics.get(e.topic)||{topic:e.topic,total:0,attempted:0,success:0,failure:0,delayed:0};s.total++;if(h.length)s.attempted++;
   for(const x of daily.values()){const w=Math.pow(.5,Math.max(0,(now-x.at)/DAY)/45)/Math.max(1,a.exams[exam].evidence.length);if(x.outcome==='ok'){s.success+=w*(x.delayed?1.3:.6);if(x.delayed)s.delayed++}else s.failure+=w*(x.outcome==='wrong'?1:.7)}
   topics.set(e.topic,s);const last=h.at(-1);if(last&&last.outcome!=='ok'&&['概念','模型','条件'].includes(last.error))weakErrors.add(e.topic);
  }
 }
 for(const s of topics.values()){s.mastery=(1+s.success)/(2+s.success+s.failure);s.state=!s.attempted?'未诊断':s.mastery<.45?'薄弱':s.delayed<2?'待延迟检验':'有复测证据'}
 const median=xs=>[...xs].sort((a,b)=>a-b)[Math.floor(xs.length/2)],candidates=[];
 for(const a of eligible){
  const q=byId.get(a.id),r=records[a.id]||{},e=a.exams[exam],h=practiceEvents(r),last=h.at(-1),due=Number.isFinite(r.due)&&r.due<=now;
  if(r.status&&Number.isFinite(r.due)&&!due||r.status==='ok'&&!due)continue;
  const states=e.evidence.map(x=>topics.get(x.topic)),unseen=states.some(s=>!s.attempted),weak=states.some(s=>s.mastery<.45||weakErrors.has(s.topic));
  const lane=due?'到期复测':unseen?'基础诊断':weak?'薄弱补练':'巩固应用',reasons=[];
  let score=25+35*(states.length?Math.max(...states.map(s=>1-s.mastery)):.5);
  if(due){score+=120+Math.min(25,Math.max(0,(now-r.due)/DAY));reasons.push('到期检验延迟记忆')}
  if(last&&last.outcome!=='ok'){score+=20;reasons.push(last.outcome==='assisted'?'上次借助答案，需独立检验':'上次做错，先补课再复测')}
  if(unseen){score+=15;reasons.push('主题尚未诊断')}
  if(weak){score+=20;reasons.push('主题存在错误或概念/模型/条件薄弱记录')}
  if(q.type==='思考题'&&(unseen||states.some(s=>weakErrors.has(s.topic)))){score+=18;reasons.push('先检查概念和适用条件')}
  if(q.type==='习题'&&!unseen&&!states.some(s=>weakErrors.has(s.topic))){score+=12;reasons.push('练习计算应用')}
  if(e.tier==='概念了解'){score-=20;reasons.push('了解层次，控制投入')}
  if(e.tier.startsWith('已核验')){score+=12;reasons.push('相关性已核验')}else reasons.push('自动初筛候选，需核对原页');
  // 模型相关性判断（可选富集）：加分/减分并给出理由；这是模型判断，不等于人工核验。
  const rel=a.relevance;
  if(rel){
   const lvl=rel.level,relScore=Number.isFinite(rel.relevant)?rel.relevant:null;
   if(lvl==='high'){score+=14;reasons.push('模型判断为高相关'+(relScore!=null?`（${relScore}）`:''))}
   else if(lvl==='medium'){score+=4;reasons.push('模型判断为中等相关'+(relScore!=null?`（${relScore}）`:''))}
   else if(lvl==='low'){score-=10;reasons.push('模型判断为低相关，控制投入')}
   else if(lvl==='none'){score-=30;reasons.push('模型判断与考研关联弱')}
   const fit=rel.exam_fit||[];
   if(fit.length&&!fit.map(String).includes(exam)){score-=8;reasons.push('模型认为更适配 '+fit.join('/'))}
  }
  const own=h.filter(x=>x.minutes>0&&x.minutes<=180).map(x=>x.minutes),sample=times[a.type]||[];
  const minutes=Math.max(2,Math.ceil(own.length?median(own):sample.length>=3?median(sample):Number(a.estimated_minutes)||15));
  const timeBasis=own.length?'本题历史用时':sample.length>=3?'同题型个人用时中位数':'题型初始估时';
  const text=(q.question_ocr||'').replace(/^\s*[\dA-D]+\s*[-~－]\s*\d+[.．]?/,'').replace(/\s+/g,''),grams=new Set();for(let i=0;i<text.length-3;i++)grams.add(text.slice(i,i+4));
  candidates.push({analysis:a,question:q,score,reasons,lane,minutes,timeBasis,grams});
 }
 const target=budget*(mode==='review'?.85:mode==='new'?.3:.6),selected=[],counts=new Map(),remaining=[...candidates];let used=0,review=0,concept=0,thought=0;
 const overlap=(a,b)=>{if(a.size<8||b.size<8)return 0;let n=0;for(const x of a)if(b.has(x))n++;return n/Math.min(a.size,b.size)};
 while(remaining.length){let winner=null,best=-Infinity;
  for(const c of remaining){
   if(used+c.minutes>budget||c.analysis.exams[exam].tier==='概念了解'&&concept>=1)continue;
   if(selected.some(s=>overlap(c.grams,s.grams)>.8))continue;
   const ts=c.analysis.exams[exam].evidence.map(x=>x.topic);if(c.lane!=='到期复测'&&ts.length&&ts.every(t=>(counts.get(t)||0)>=2))continue;
   let score=c.score;
   if(c.lane==='到期复测'&&review>=target&&remaining.some(x=>x.lane!=='到期复测'&&used+x.minutes<=budget))score-=140;
   score-=18*Math.min(...(ts.length?ts.map(t=>counts.get(t)||0):[0]));
   if(c.analysis.type==='思考题'&&thought>=Math.ceil(Math.max(1,selected.length)*.5)&&remaining.some(x=>x.analysis.type==='习题'&&used+x.minutes<=budget))score-=32;
   let hash=0;for(const ch of c.analysis.id+Math.floor(now/DAY))hash=(hash*31+ch.charCodeAt(0))>>>0;score+=(hash%1000)/1000;
   if(score>best){best=score;winner=c}
  }
  if(!winner)break;remaining.splice(remaining.indexOf(winner),1);selected.push(winner);used+=winner.minutes;
  if(winner.lane==='到期复测')review+=winner.minutes;if(winner.analysis.type==='思考题')thought++;if(winner.analysis.exams[exam].tier==='概念了解')concept++;
  for(const x of winner.analysis.exams[exam].evidence)counts.set(x.topic,(counts.get(x.topic)||0)+1);
 }
 return {selected:selected.map(({grams,...r})=>r),estimatedMinutes:used,eligible:eligible.length,candidates:candidates.length,topics:[...topics.values()],reviewMinutes:review,version:'adaptive-v2'};
}
if(typeof module!=='undefined')module.exports={recommendPractice,recordPractice,practiceEvents};
