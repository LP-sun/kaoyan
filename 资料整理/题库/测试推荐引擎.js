const assert=require('assert'),fs=require('fs'),vm=require('vm');
const {recommendPractice,recordPractice,practiceEvents}=require('./推荐引擎v2.js');
const DAY=86400000,now=20000*DAY;
let r=recordPractice({note:'保留笔记'},'ok',{now,minutes:8});
assert.equal(r.streak,1);assert.equal(r.due,now+3*DAY);assert.equal(r.note,'保留笔记');
r=recordPractice(r,'ok',{now:now+DAY});assert.equal(r.streak,1);assert.equal(r.history.at(-1).delayed,false);
r=recordPractice(r,'ok',{now:r.due});assert.equal(r.streak,2);assert.equal(r.due,r.last+14*DAY);
r=recordPractice(r,'ok',{now:r.due});assert.equal(r.streak,3);assert.equal(r.due,r.last+30*DAY);
r=recordPractice(r,'assisted',{now:r.due,error:'模型'});assert.equal(r.streak,0);assert.equal(r.status,'assisted');assert.equal(r.due,r.last+2*DAY);
assert.equal(practiceEvents({status:'wrong',last:now}).length,1);
const q=JSON.parse(fs.readFileSync(__dirname+'/教材习题.json','utf8')),a=JSON.parse(fs.readFileSync(__dirname+'/考研相关性.json','utf8')).questions;
for(const exam of ['651','803']){
 const records={},snapshot=JSON.stringify(records),base=recommendPractice(q,a,records,{exam,minutes:60,now});
 assert(base.selected.length>0);assert(base.estimatedMinutes<=60);assert.equal(JSON.stringify(records),snapshot);
 assert.deepEqual(base,recommendPractice(q,a,records,{exam,minutes:60,now}));
 assert(base.selected.every(c=>c.analysis.book_id!=='BK08'&&!c.analysis.dependency_warning));
 const id=base.selected[0].analysis.id;
 records[id]={status:'wrong',last:now-4*DAY,due:now-DAY};
 assert.equal(recommendPractice(q,a,records,{exam,minutes:60,now}).selected[0].analysis.id,id);
 records[id].due=now+DAY;assert(!recommendPractice(q,a,records,{exam,minutes:60,now}).selected.some(c=>c.analysis.id===id));
 records[id].blocked=true;records[id].due=now-DAY;assert(!recommendPractice(q,a,records,{exam,minutes:60,now}).selected.some(c=>c.analysis.id===id));
 const topic=base.selected[0].analysis.exams[exam].evidence[0].topic;
 assert(recommendPractice(q,a,{}, {exam,minutes:60,now,focus:topic}).selected.every(c=>c.analysis.exams[exam].evidence.some(e=>e.topic===topic)));
 assert.equal(recommendPractice(q,a,{}, {exam,minutes:0,now}).selected.length,0);
 console.log(exam+'：预算、到期优先、暂停、主题筛选、旧版排除、确定性和无写入通过');
}
// 合成相同题面：检验同一批次的近似重复抑制。
const qq=[1,2].map(i=>({id:'BK01-'+i,type:'习题',question_ocr:'相同题面测试：求波函数的统计解释与归一化，列出完整条件'}));
const aa=qq.map(x=>({id:x.id,book_id:'BK01',type:'习题',estimated_minutes:10,exams:{651:{tier:'大纲候选',evidence:[{topic:'测试'}]}}}));
assert.equal(recommendPractice(qq,aa,{}, {minutes:60,now}).selected.length,1);
const timed={};for(const x of baseSafe(q,a))timed[x.id]={status:'ok',last:now-DAY,due:now+DAY,history:[{at:now-DAY,outcome:'ok',minutes:9}]};
function baseSafe(q,a){return a.filter(x=>x.book_id==='BK04'&&x.type==='习题'&&x.exams['651'].tier==='大纲候选').slice(0,3)}
assert(recommendPractice(q,a,timed,{minutes:60,now}).selected.filter(x=>x.analysis.type==='习题').every(x=>x.minutes===9));
const html=fs.readFileSync(__dirname+'/自动推荐刷题.html','utf8');for(const m of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
console.log('历史迁移、延迟检验、借助答案、近似重复、个人用时与网页脚本语法通过');

// 模型相关性：加分/减分、筛选、理由、绑定到 exam_fit 的惩罚。
{
 const mk=(id,lvl,fit)=>({id,type:'习题',question_ocr:'相关性测试题：求波函数的统计解释与归一化，写出条件'});
 const q3=['A','B','C'].map(n=>mk('BK01-'+n));
 const base=[{id:'BK01-A',book_id:'BK01',type:'习题',estimated_minutes:10,exams:{651:{tier:'大纲候选',evidence:[{topic:'T1'}]}},relevance:{level:'high',relevant:95,exam_fit:['651']}},
   {id:'BK01-B',book_id:'BK01',type:'习题',estimated_minutes:10,exams:{651:{tier:'大纲候选',evidence:[{topic:'T2'}]}},relevance:{level:'none',relevant:5,exam_fit:['651']}},
   {id:'BK01-C',book_id:'BK01',type:'习题',estimated_minutes:10,exams:{651:{tier:'大纲候选',evidence:[{topic:'T3'}]}},relevance:{level:'medium',relevant:55,exam_fit:['803']}}];
 // minRelevance=high 只留 high。
 const hi=recommendPractice(q3,base,{}, {exam:'651',minutes:999,now,minRelevance:'high'});
 assert(hi.selected.every(c=>c.analysis.relevance.level==='high'));
 // minRelevance 过滤掉 none。
 const noNone=recommendPractice(q3,base,{}, {exam:'651',minutes:999,now,minRelevance:'low'});
 assert(!noNone.selected.some(c=>c.analysis.relevance.level==='none'));
 // 题面刻意不同，避免近似重复抑制，使三题都能进。
 const ocr=['相关性测试题甲：证明角动量守恒并写出适用条件与推导步骤','相关性测试题乙：计算光栅第一级线色散与分辨本领数值','相关性测试题丙：说明熵增原理的统计意义并举例'];
 const q3b=q3.map((x,i)=>({...x,question_ocr:ocr[i]}));
 const all=recommendPractice(q3b,base,{}, {exam:'651',minutes:999,now});
 const byId=Object.fromEntries(all.selected.map(c=>[c.analysis.id,c]));
 assert(byId['BK01-A']&&byId['BK01-B']&&byId['BK01-C']);
 // high 的理由应出现“高相关”，none 的理由应出现“关联弱”。
 assert(byId['BK01-A'].reasons.some(x=>x.includes('高相关')));
 assert(byId['BK01-B'].reasons.some(x=>x.includes('关联弱')));
 // C 的 exam_fit 只列 803，在 651 下应被惩罚并提示。
 assert(byId['BK01-C'].reasons.some(x=>x.includes('803')));
 // high 分数应高于同条件 none 分数（比较原始 score）。
 assert(byId['BK01-A'].score>byId['BK01-B'].score);
 console.log('模型相关性：筛选、理由与 exam_fit 惩罚通过');
}
