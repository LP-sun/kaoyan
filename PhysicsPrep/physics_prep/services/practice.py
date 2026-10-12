"""Persistent practice controller. UI is a view, never the scheduler.

Feedback and a prepared next snapshot coexist. Only next() changes the card.
Attempt is the write-ahead truth: recover() reconciles a crash between grading
and the controller checkpoint without applying mastery a second time.
"""
from copy import deepcopy
from datetime import datetime
from sqlalchemy import select
from ..clock import naive_utcnow, to_iso
from ..database.models import PracticeState, Attempt, ExamSession, Question, MasteryRecord, ReviewSchedule
from ..diagnosis.selector import select_question, AUTO_GRADED_TYPES
from ..questions.eligibility import is_practice_eligible as eligible

ERROR_TYPES = ('概念错误','模型选择错误','方程建立错误','符号或方向错误','数学计算错误','计算粗心','单位或量纲错误','边界条件错误','物理条件遗漏','记忆缺失','暂无法确定')
from ..questions.candidates import MODEL_TOPICS


class PracticeSessionController:
    MAX_REMEDY_DEPTH = 3
    MAX_REMEDY_SECONDS = 600
    MAX_GENERATION_CALLS = 2

    def __init__(self, service, client_factory=None):
        self.service = service
        self.client_factory = client_factory
        tree = {t['id'] for t in service.repository.topic_tree()}
        if {'PHY-MECH-ROT','PHY-MECH-DYN-001'} <= tree and 'PHY-MECH-ROT-TORQUE' not in tree:
            service.repository.save_topics([{'id':'PHY-MECH-ROT-TORQUE','name':'力矩大小与力臂',
                'parent_id':'PHY-MECH-ROT','prerequisite_ids':['PHY-MECH-DYN-001'],
                'source_references':['基础定义诊断节点：τ=r×F；不是官方大纲新增条目。']}])
        if {'PHY-MECH-ROT','PHY-MECH-ROT-002','PHY-MECH-KIN-001'} <= tree:
            current={t['id'] for t in service.repository.topic_tree()}
            additions=[]
            if 'PHY-MECH-ROT-NOSLIP' not in current:
                additions.append({'id':'PHY-MECH-ROT-NOSLIP','name':'绳与轮缘不滑动','parent_id':'PHY-MECH-ROT',
                    'prerequisite_ids':['PHY-MECH-KIN-001','PHY-MECH-ROT-002'],
                    'source_references':['固定轮心时，绳速v=ωR，R恒定则a=αR；与轮心平动区分。']})
            if 'PHY-MECH-ROT-PULLEY' not in current:
                additions.append({'id':'PHY-MECH-ROT-PULLEY','name':'有转动惯量的绕绳滑轮','parent_id':'PHY-MECH-ROT',
                    'prerequisite_ids':['PHY-MECH-DYN-001','PHY-MECH-ROT-TORQUE','PHY-MECH-ROT-001','PHY-MECH-ROT-002','PHY-MECH-ROT-NOSLIP'],
                    'source_references':['由mg−T=ma、TR=Iα和a=αR建立模型依赖；不冒称官方大纲条目。']})
            if additions:
                service.repository.save_topics(additions)

    def _load(self, sid):
        with self.service.factory() as s:
            self.service._session(s, sid)
            row = s.get(PracticeState, sid)
            if not row:
                raise ValueError('该会话不是连续刷题会话，请点击开始刷题。')
            return deepcopy(row.payload)

    def _client(self):
        client=self.client_factory()
        from ..llm.client import OfficialGenAIClient
        if isinstance(client,OfficialGenAIClient):
            from dataclasses import replace
            settings=replace(client.settings,timeout=min(10,client.settings.timeout),max_retries=0,
                model_fallbacks=client.settings.model_fallbacks[:1])
            if settings==client.settings:
                return client
            return OfficialGenAIClient(settings)
        return client

    def _save(self, sid, data):
        with self.service.factory.begin() as s:
            s.connection().exec_driver_sql('BEGIN IMMEDIATE')
            row = s.get(PracticeState, sid)
            revision=data.get('_revision',0)
            if row:
                if row.payload.get('_revision',0)!=revision:
                    raise ValueError('刷题状态已被其他窗口更新，请点击继续刷题恢复。')
                data['_revision']=revision+1
                row.payload = deepcopy(data)
            else:
                data['_revision']=1
                s.add(PracticeState(session_id=sid, payload=deepcopy(data)))

    def start(self, subject='auto', mode='adaptive', chapter=None):
        if subject not in ('auto','general','quantum'):
            raise ValueError('请选择普通物理、量子力学或自动安排。')
        if mode not in ('adaptive','foundation','chapter','weakness','review'):
            raise ValueError('未知刷题模式。')
        if mode == 'chapter' and not chapter:
            raise ValueError('指定章节模式需要选择章节。')
        sid = self.service.start(subject='quantum' if subject == 'quantum' else None)
        data = {'session_id':sid,'phase':'READY','subject':subject,'mode':mode,'chapter':chapter,
            'started_at':to_iso(naive_utcnow()),'ended_at':None,'elapsed_seconds':0,
            'current_id':None,'hint_level':0,'attempts':0,'independent':True,
            'recent_errors':[],'remedy':None,'prepared':None,'last_feedback':None,
            'processed_attempt':0,'generation_calls':0,'generation_events':[], 'trace':['READY']}
        self._save(sid,data)
        return self.next(sid)

    def resume(self):
        with self.service.factory() as s:
            sid = s.scalar(select(PracticeState.session_id).join(ExamSession).where(
                ExamSession.user_id == self.service.user_id, ExamSession.status == 'active').order_by(ExamSession.started_at.desc()))
        return self.view(sid) if sid else None

    def _history(self, sid):
        with self.service.factory() as s:
            rows = list(s.scalars(select(Attempt).where(Attempt.user_id == self.service.user_id).order_by(Attempt.id)))
        return rows, [r for r in rows if r.session_id == sid]

    def _candidates(self, data):
        qs = [q for q in self.service.list_questions() if eligible(q)]
        if data['subject'] == 'general':
            qs = [q for q in qs if q['subject'] != 'quantum']
        elif data['subject'] == 'quantum':
            qs = [q for q in qs if q['subject'] == 'quantum']
        if data.get('chapter'):
            ids = {data['chapter']}
            for _ in range(20):
                new = ids | {t['id'] for t in self.service.repository.topic_tree() if t['parent_id'] in ids}
                if new == ids:
                    break
                ids = new
            qs = [q for q in qs if set(q['topic_ids']) & ids]
        return qs

    def _generate(self, data, target, seen):
        model = next((m for m,t in MODEL_TOPICS.items() if t == target), None)
        if not model:
            return None
        with self.service.factory() as s:
            prior = [r.snapshot for r in s.scalars(select(Attempt).where(Attempt.session_id==data['session_id']))]
        signatures = {(q.get('generation',{}).get('model'),str(sorted(q.get('generation',{}).get('parameters',{}).items()))) for q in prior if q.get('generation')}
        from ..questions.generation import generate, MODEL_PERIODS
        for variant in range(MODEL_PERIODS[model]):
            q = generate(model,target,variant)
            if q['id'] in seen or (model,str(sorted(q['generation']['parameters'].items()))) in signatures:
                continue
            existing = next((r for r in self.service.list_questions() if r['id'] == q['id']), None)
            if existing and not eligible(existing):
                existing=self.service.store_generated(q)
                if not eligible(existing):
                    continue
            # LLM proposes a model/variant; canonical executable validation has
            # final authority. A failure cannot put arbitrary text in the pool.
            if not existing and self.client_factory and data['generation_calls'] < self.MAX_GENERATION_CALLS:
                from ..questions.candidates import generate_candidate
                data['generation_calls'] += 1
                self._save(data['session_id'],data)
                try:
                    profile=next((r for r in self.service.dashboard()['mastery'] if r['topic_id']==target),{})
                    prerequisite_ids=next((t['prerequisite_ids'] for t in self.service.repository.topic_tree() if t['id']==target),[])
                    context={'subject':q['subject'],'mastery_heuristic':profile.get('estimate'),
                        'mastery_is_calibrated_probability':False,'target_difficulty':q['difficulty'],
                        'question_type':q['question_type'],'prerequisite_ids':prerequisite_ids,
                        'recent_errors':data['recent_errors'][-3:],
                        'recent_questions':[{'id':p['id'],'topic_ids':p['topic_ids']} for p in prior[-3:]]}
                    proposed = generate_candidate(self._client(),target,[model],variant,context)
                    data['generation_events'].append(proposed.get('proposal_evidence', proposed.get('generation',{})))
                    live_proposal = next((r for r in self.service.list_questions() if r['id']==proposed['id']),None)
                    if (live_proposal is None or eligible(live_proposal)) and proposed['id'] not in seen and (model,str(sorted(proposed['generation']['parameters'].items()))) not in signatures:
                        q = proposed
                except Exception as exc:
                    data['generation_events'].append({'status':'rejected','error':type(exc).__name__})
            return self.service.store_generated(q)
        return None

    def _choose(self, sid, data):
        all_rows, rows = self._history(sid)
        seen = {r.question_id for r in rows} | set(data.get('skipped_ids',[]))
        qs = self._candidates(data)
        signatures={(r.snapshot.get('generation',{}).get('model'),str(sorted(r.snapshot.get('generation',{}).get('parameters',{}).items()))) for r in rows if r.snapshot.get('generation')}
        qs=[q for q in qs if not q.get('generation') or (q['generation']['model'],str(sorted(q['generation'].get('parameters',{}).items()))) not in signatures]
        tree = {t['id']:t for t in self.service.repository.topic_tree()}
        records = {r['topic_id']:r for r in self.service.dashboard()['mastery']}
        due_all = {r['topic_id'] for r in self.service.dashboard()['due_reviews']}
        due={t for t in due_all if not records.get(t,{}).get('last_practiced') or
            (naive_utcnow()-datetime.fromisoformat(records[t]['last_practiced']).replace(tzinfo=None)).total_seconds()>=86400}
        if data['mode']=='review' and not due:
            data['notice']='当前暂无可独立延迟检验的到期题；先练不同考点，原复测时间仍保留。'
        remedy = data.get('remedy')
        if remedy:
            if remedy['stage'] == 'return':
                q = deepcopy(remedy['origin'])
                live = next((r for r in self.service.list_questions() if r['id']==q['id']),None)
                if live is None or not eligible(live):
                    data['remedy']=None
                    return self._choose(sid,data)
                q.pop('hint_level',None)
                q['prior_exposure']=True
                q['recommendation_reason'] = '前置知识变式已独立答对，返回原知识目标；本次仍需独立验证。'
                return q
            target = remedy['target']
            pool = [q for q in self.service.list_questions() if eligible(q) and target in q['topic_ids'] and q['id'] not in seen and q['difficulty'] <= 2]
            signatures={(r.snapshot.get('generation',{}).get('model'),str(sorted(r.snapshot.get('generation',{}).get('parameters',{}).items()))) for r in rows if r.snapshot.get('generation')}
            pool=[q for q in pool if not q.get('generation') or (q['generation']['model'],str(sorted(q['generation'].get('parameters',{}).items()))) not in signatures]
            # Verification must differ from the last rendered statement.
            pool.sort(key=lambda q:(bool(q.get('generation')),q['difficulty'],q['id']))
            q = pool[0] if pool else self._generate(data,target,seen)
            if q:
                return q | {'recommendation_reason':f"{'变式验证' if remedy['stage']=='verification' else '前置补救'}：先独立检验{tree.get(target,{}).get('name',target)}；仅凭最终答案无法断定具体错因。"}
            data['remedy'] = None
            data['notice'] = '该前置考点暂无可信基础题，切换其他考点，保留待复测目标。'
        unseen = [q for q in qs if q['id'] not in seen]
        if data['mode'] == 'review':
            review_pool = [q for q in unseen if set(q['topic_ids']) & due]
            unseen = review_pool or unseen
        if data['mode'] == 'weakness':
            weak = {r['topic_id'] for r in self.service.dashboard()['weak_topics']}
            weak_pool = [q for q in unseen if set(q['topic_ids']) & weak]
            unseen = weak_pool or unseen
        if data['mode'] == 'foundation' and not rows:
            foundation = [q for q in unseen if q['difficulty'] == min((x['difficulty'] for x in unseen),default=1)]
            unseen = foundation or unseen
        history = [{'question_id':r.question_id,'status':r.status,'topic_ids':r.snapshot['topic_ids'],
            'hint_level':r.feedback.get('hint_level',0),'error_category':r.feedback.get('error_category')} for r in all_rows[-100:]]
        if unseen:
            # Use global recent behaviour for difficulty but exclude this
            # session's repeats. Prefer existing records before generating.
            return select_question(unseen,history,records,{t:v['prerequisite_ids'] for t,v in tree.items()},due)
        supported = [t for t in MODEL_TOPICS.values() if t in tree and
            (data['subject'] != 'quantum' or t.startswith('PHY-QM')) and
            (data['subject'] != 'general' or not t.startswith('PHY-QM'))]
        if data.get('chapter'):
            targets = {t for q in self._candidates(data) for t in q['topic_ids']}
            supported = [t for t in supported if t in targets or t == data['chapter']]
        # Rotate model families; parameter changes alone aren't new coverage.
        last_topic = rows[-1].snapshot['topic_ids'][0] if rows else None
        supported.sort(key=lambda t:(t == last_topic, sum(t in r.snapshot['topic_ids'] for r in rows),t))
        for target in supported:
            if target=='PHY-MECH-ROT-PULLEY' and data.get('chapter')!=target and any(
                records.get(p,{}).get('estimate') is None or records.get(p,{}).get('estimate',0)<.5
                for p in tree[target]['prerequisite_ids']):
                continue
            q = self._generate(data,target,seen)
            if q:
                return q | {'recommendation_reason':'现有合适题已练过；用经过程序校验的基础变式继续，尚需延迟独立复测。'}
        if data.get('chapter'):
            requested=data['chapter']
            data['coverage_gaps']=list(set(data.get('coverage_gaps',[])+[requested]))
            data['chapter']=None; data['mode']='adaptive'
            data['notice']='所选考点暂缺可信题，先转为本科学科的基础练习；不将该考点标为已掌握。'
            q=self._choose(sid,data)
            if q:
                return q | {'recommendation_reason':data['notice']+' '+q.get('recommendation_reason','')}
        return None

    def _update_after_attempt(self, sid, data, a):
        if a.id <= data.get('processed_attempt',0):
            return
        data['processed_attempt'] = a.id
        data['attempts'] += 1
        data['last_feedback'] = deepcopy(a.feedback)
        data['elapsed_seconds'] += a.feedback.get('elapsed_seconds',0)
        data['phase'] = 'FEEDBACK'
        data['trace'] = (data['trace']+['FEEDBACK'])[-60:]
        data['current_id'] = a.question_id
        data.pop('notice',None)
        remedy = data.get('remedy')
        independent_ok = a.status == 'correct' and a.feedback.get('independent',True)
        if remedy and (remedy['depth'] >= self.MAX_REMEDY_DEPTH or
                (naive_utcnow()-datetime.fromisoformat(remedy['started_at']).replace(tzinfo=None)).total_seconds() >= self.MAX_REMEDY_SECONDS):
            data['remedy'] = None
            data['notice'] = '补救已达到深度或时间上限，先换考点，原目标留待复测。'
            remedy = None
        elif remedy:
            if independent_ok or (remedy['stage']=='return' and a.status=='correct'):
                if remedy['stage'] == 'remediation':
                    remedy['stage'] = 'verification'
                elif remedy['stage'] == 'verification':
                    remedy['stage'] = 'return'
                else:
                    data['remedy'] = None
            else:
                remedy['depth'] += 1
                remedy['stage'] = 'remediation'
                pre = next((t['prerequisite_ids'] for t in self.service.repository.topic_tree() if t['id'] == remedy['target']),[])
                remedy['target'] = pre[0] if pre else remedy['target']
        elif a.status == 'incorrect' or a.feedback.get('hint_level'):
            tree = {t['id']:t for t in self.service.repository.topic_tree()}
            primary = a.snapshot['topic_ids'][0]
            pre = tree.get(primary,{}).get('prerequisite_ids',[])
            target = 'PHY-MECH-ROT-TORQUE' if primary.startswith('PHY-MECH-ROT') else (pre[0] if pre else primary)
            if target not in tree:
                target = pre[0] if pre else primary
            data['remedy'] = {'origin':deepcopy(a.snapshot),'target':target,'stage':'remediation',
                'depth':1,'started_at':to_iso(naive_utcnow())}
        if a.status == 'incorrect':
            data['recent_errors'] = (data['recent_errors']+[{'question_id':a.question_id,
                'topic_ids':a.snapshot['topic_ids'],'type':a.feedback.get('error_category','暂无法确定')}])[-8:]
        data['prepared'] = self._choose(sid,data)
        self._save(sid,data)

    def _recover(self, sid, data):
        _,rows = self._history(sid)
        for a in rows:
            self._update_after_attempt(sid,data,a)
        return data

    def view(self, sid):
        with self.service.lock:
            data = self._recover(sid,self._load(sid))
            with self.service.factory() as s:
                row = self.service._session(s,sid)
                question = self.service._public(row.current_snapshot,data['attempts']) if row.current_snapshot else None
                if question is None and data['phase'] == 'FEEDBACK':
                    last = s.scalar(select(Attempt).where(Attempt.session_id==sid).order_by(Attempt.id.desc()))
                    if last:
                        question = self.service._public(last.snapshot,data['attempts'])
                if row.current_snapshot:
                    data['hint_level'] = row.current_snapshot.get('hint_level',0)
                    data['independent'] = not bool(data['hint_level'] or row.current_snapshot.get('prior_exposure'))
                    snapshot=deepcopy(row.current_snapshot)
                    activated_id=row.current_question_id
                else:
                    snapshot=None
                    activated_id=None
            # Recover an activation committed just before its state checkpoint.
            # Only a user next() action installs a snapshot; this never advances
            # a feedback-only session on its own.
            if snapshot and data['phase']!='SAVED' and (data['current_id']!=activated_id or data['phase'] in ('READY','FEEDBACK')):
                data['current_id']=activated_id
                data['prepared']=None
                stage=snapshot.get('remediation_stage')
                data['phase']='VERIFICATION' if stage=='verification' else 'REMEDIATION' if stage=='remediation' else 'QUESTION'
                data['trace']=(data['trace']+['RECOVERED_QUESTION'])[-60:]
                self._save(sid,data)
            summary=self.service.report(sid)
            summary['needs_independent_retest']=sorted(set(summary['needs_independent_retest']) | set(data.get('pending_targets',[])))
            summary['unable_to_start_count']=data.get('unable_to_start_count',0)
            summary['coverage_gaps']=data.get('coverage_gaps',[])
            return {'session_id':sid,'question':question, 'state':{k:v for k,v in data.items()
                if k not in ('prepared','remedy','generation_events','_revision')}, 'remedy':{k:v for k,v in (data.get('remedy') or {}).items() if k != 'origin'},
                'next_reason':(data.get('prepared') or {}).get('recommendation_reason',''),
                'summary':summary}

    def next(self, sid):
        with self.service.lock:
            data = self._recover(sid,self._load(sid))
            if data['phase'] == 'SAVED':
                return self.view(sid)
            with self.service.factory() as s:
                current = self.service._session(s,sid)
                if current.current_snapshot:
                    live=s.get(Question,current.current_question_id)
                    active_eligible=live is not None and eligible(live.payload)
                    if active_eligible:
                        return self.view(sid)
            if current.current_snapshot and not active_eligible:
                with self.service.factory.begin() as s:
                    active=self.service._session(s,sid)
                    active.current_snapshot=None; active.current_question_id=None
                data['prepared']=None
                data['notice']='已跳过暂停题目；不写入确定性成绩。'
            q = data.get('prepared') or self._choose(sid,data)
            if not q:
                return self.finish(sid)
            # A reported/revoked cached question must not be activated.
            invalid=False
            already_active=False
            with self.service.factory.begin() as s:
                s.connection().exec_driver_sql('BEGIN IMMEDIATE')
                row = s.get(Question,q['id'])
                if not row or not eligible(row.payload):
                    invalid=True
                else:
                    current = self.service._session(s,sid)
                    if current.current_snapshot:
                        already_active=True
                    else:
                        current.current_question_id = q['id']
                        current.current_snapshot = q | {'practice_started_at':to_iso(naive_utcnow()), 'hint_level':0,
                            'remediation_stage':(data.get('remedy') or {}).get('stage')}
            if already_active:
                return self.view(sid)
            if invalid:
                data['prepared']=self._choose(sid,data)
                self._save(sid,data)
                return self.next(sid) if data['prepared'] else self.finish(sid)
            data['prepared'] = None
            data['current_id'] = q['id']
            data['hint_level'] = 0
            data.pop('revealed_after_feedback',None)
            data['independent'] = True
            remedy = data.get('remedy')
            if remedy:
                data.pop('notice',None)
            data['phase'] = 'VERIFICATION' if remedy and remedy['stage']=='verification' else 'REMEDIATION' if remedy and remedy['stage']=='remediation' else 'QUESTION'
            data['trace'] = (data['trace']+['NEXT',data['phase'],'ANSWERING'])[-60:]
            self._save(sid,data)
            return self.view(sid)

    def submit(self, sid, qid, answer, token):
        with self.service.lock:
            data = self._load(sid)
            if data['phase'] == 'SAVED':
                raise ValueError('本轮已经结束，请开始新会话。')
            from .tutor import classify
            if isinstance(answer,str) and classify(answer) == 'help':
                guidance = self.hint(sid,qid,text=answer)
                return self.view(sid) | {'guidance':guidance['teacher']}
            feedback = self.service.submit(sid,qid,answer,token)
            with self.service.factory() as s:
                a=s.scalar(select(Attempt).where(Attempt.user_id==self.service.user_id,Attempt.token==token))
            process_answer = a and (a.snapshot['question_type'] not in AUTO_GRADED_TYPES or
                (a.status=='uncertain' and isinstance(answer,str) and ('=' in answer or '\n' in answer)))
            if process_answer and self.client_factory and not a.feedback.get('process_assessment'):
                from ..diagnosis.process_assessment import assess_process
                try:
                    assessment=assess_process(self._client(),a.snapshot,answer)
                except Exception:
                    assessment={'state':'unavailable','assessment':'uncertain','next_action':'请写出关键方程或请求提示。'}
                with self.service.factory.begin() as s:
                    saved=s.get(Attempt,a.id)
                    saved.feedback=saved.feedback | {'process_assessment':assessment}
                    feedback=saved.feedback
            return self.view(sid) | {'feedback':feedback}

    def hint(self, sid, qid, full=False, text='提示一下'):
        with self.service.lock:
            data = self._load(sid)
            from .tutor import classify
            if classify(text)=='final' and not full:
                from uuid import uuid4
                answer=text.split('：',1)[-1] if '：' in text else text.split(':',1)[-1]
                view=self.submit(sid,qid,answer.strip(),'practice-chat-'+uuid4().hex)
                fb=view['feedback']
                return {'teacher':f"判分：{fb['status']}。{fb['error_analysis']} 点击下一题继续。",
                    'hint_level':fb['hint_level'],'submitted':True}
            if data['phase'] in ('SAVED','FEEDBACK'):
                if full and data.get('last_feedback'):
                    data['revealed_after_feedback']=True
                    self._save(sid,data)
                    return {'teacher':data['last_feedback']['solution'],'hint_level':4}
                raise ValueError('当前题已提交或会话已结束，请先进入下一题。')
            data['phase']='HINT'
            data['trace']=(data['trace']+['HINT'])[-60:]
            self._save(sid,data)
            result = self.service.tutor(sid,qid,text,self._client() if self.client_factory and text != '提示一下' else None,full)
            result['teacher']=f"L{result['hint_level']} · "+result['teacher']
            data['hint_level'] = result['hint_level']
            data['independent'] = False
            data['phase']='ANSWERING'
            data['trace'] = (data['trace']+['HINT','ANSWERING'])[-60:]
            self._save(sid,data)
            return result

    def try_again(self, sid):
        with self.service.lock:
            data=self._load(sid)
            if data['phase']!='FEEDBACK':
                raise ValueError('请先提交当前题再继续尝试。')
            with self.service.factory.begin() as s:
                a=s.scalar(select(Attempt).where(Attempt.session_id==sid).order_by(Attempt.id.desc()))
                row=self.service._session(s,sid)
                q=deepcopy(a.snapshot)
                if data.get('revealed_after_feedback'):
                    q['hint_level']=4
                q['practice_started_at']=to_iso(naive_utcnow())
                row.current_question_id=q['id']; row.current_snapshot=q
            data['prepared']=None
            data['phase']='ANSWERING'
            # A retry of the same seen question is not transfer verification.
            data['remedy']=None
            data['trace']=(data['trace']+['ANSWERING'])[-60:]
            self._save(sid,data)
            return self.view(sid)

    def remediate_now(self, sid):
        """Observed inability to start, not a fabricated incorrect answer."""
        with self.service.lock:
            data=self._load(sid)
            if data['phase']=='FEEDBACK':
                return self.next(sid)
            if data['phase']=='SAVED':
                raise ValueError('本轮已经结束。')
            tree={t['id']:t for t in self.service.repository.topic_tree()}
            with self.service.factory.begin() as s:
                s.connection().exec_driver_sql('BEGIN IMMEDIATE')
                current=self.service._session(s,sid)
                q=deepcopy(current.current_snapshot)
                if not q:
                    raise ValueError('当前没有待答题。')
                checkpoint=s.get(PracticeState,sid)
                if checkpoint.payload.get('_revision',0)!=data.get('_revision',0):
                    raise ValueError('状态已更新，请继续刷题恢复。')
                primary=q['topic_ids'][0]
                pre=tree.get(primary,{}).get('prerequisite_ids',[])
                target='PHY-MECH-ROT-TORQUE' if primary.startswith('PHY-MECH-ROT') else pre[0] if pre else primary
                previous=data.get('remedy')
                depth=previous['depth']+1 if previous else 1
                if previous:
                    pre=tree.get(previous['target'],{}).get('prerequisite_ids',[])
                    target=pre[0] if pre else previous['target']
                origin=previous['origin'] if previous else q
                if depth>self.MAX_REMEDY_DEPTH:
                    data['remedy']=None; data['chapter']=None; data['mode']='adaptive'
                    data['notice']='基础回溯已达到上限，先切换其他考点；原目标仍保留复测。'
                else:
                    data['remedy']={'origin':origin,'target':target,'stage':'remediation','depth':depth,
                        'started_at':previous['started_at'] if previous else to_iso(naive_utcnow())}
                data['pending_targets']=list(set(data.get('pending_targets',[])+origin['topic_ids']))
                for topic in origin['topic_ids']:
                    schedule=s.get(ReviewSchedule,(self.service.user_id,topic))
                    if not schedule:
                        from datetime import timedelta
                        s.add(ReviewSchedule(user_id=self.service.user_id,topic_id=topic,
                            due_at=naive_utcnow()+timedelta(days=1),interval_days=1))
                data['skipped_ids']=list(set(data.get('skipped_ids',[])+[q['id']]))
                data['unable_to_start_count']=data.get('unable_to_start_count',0)+1
                data['phase']='REMEDIATION'; data['prepared']=None
                data['_revision']=data.get('_revision',0)+1
                checkpoint.payload=data
                current.current_snapshot=None; current.current_question_id=None
            return self.next(sid)

    def record_error(self, sid, category):
        if category not in ERROR_TYPES:
            raise ValueError('请选择已定义的错误类别。')
        with self.service.lock:
            data=self._load(sid)
            if data['phase']!='FEEDBACK':
                raise ValueError('请在当前题提交后修改错因。')
            with self.service.factory.begin() as s:
                a=s.scalar(select(Attempt).where(Attempt.session_id==sid).order_by(Attempt.id.desc()))
                if not a or a.status=='correct':
                    raise ValueError('当前题没有需要归因的错误。')
                a.feedback=a.feedback | {'error_category':category,'error_source':'student'}
                data['last_feedback']=deepcopy(a.feedback)
                if data['recent_errors']:
                    data['recent_errors'][-1]['type']=category
            if category in ('数学计算错误','计算粗心'):
                data['remedy']=None
                data['notice']='已按你的归因跳过整段概念补救；后续用不同题目确认，原题仍保留复测。'
                data['prepared']=self._choose(sid,data)
            self._save(sid,data)
            return self.view(sid)

    def finish(self, sid):
        with self.service.lock:
            data = self._recover(sid,self._load(sid))
            data['phase'] = 'SAVED'
            data['ended_at'] = to_iso(naive_utcnow())
            data['prepared'] = None
            data['trace'] = (data['trace']+['SUMMARY','SAVED'])[-60:]
            self._save(sid,data)
            with self.service.factory.begin() as s:
                self.service._session(s,sid).status = 'completed'
            return self.view(sid)
