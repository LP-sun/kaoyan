import csv
import json
import sqlite3
import threading
from pathlib import Path
from uuid import uuid4
from datetime import timedelta, datetime
from sqlalchemy import select, func
from ..clock import naive_utcnow, to_iso
from ..database.session import initialize_database
from ..database.models import ExamSession, Attempt, MasteryRecord, ReviewSchedule, Topic, Question, QuestionMark, QuestionTopic
from ..questions.repository import Repository
from ..diagnosis.selector import select_question
from ..diagnosis.mastery import update_mastery
from ..diagnosis.engine import error_analysis


class LearningService:
    """单用户本地学习服务：所有学习记录都落库，不用前端状态保存进度。"""

    def __init__(self, db_path, seed_dir=None):
        self.path = Path(db_path).resolve()
        self.engine, self.factory = initialize_database(self.path)
        self.repository = Repository(self.factory)
        from .locks import database_lock
        self.lock = database_lock(self.path)
        self.user_id = 'local'
        if seed_dir:
            seed_dir = Path(seed_dir)
            with self.factory() as session:
                topics_empty = session.scalar(select(func.count()).select_from(Topic)) == 0
            if topics_empty:
                self.repository.save_topics(json.loads((seed_dir / 'seed_topics.json').read_text(encoding='utf-8')))
            with self.factory() as session:
                questions_empty = session.scalar(select(func.count()).select_from(Question)) == 0
            if questions_empty:
                self.repository.import_questions(seed_dir / 'seed_questions.json')

    # ---------------------------------------------------------------- 诊断会话

    def start(self, subject=None, chapter=None, topic_id=None, question_id=None):
        """开始一次诊断。冻结模拟卷与未核验题目不能作为诊断题。"""
        sid = uuid4().hex
        snapshot = None
        if question_id:
            matches = [q for q in self.repository.list_questions() if q['id'] == question_id]
            from ..questions.eligibility import is_practice_eligible
            if not matches or not is_practice_eligible(matches[0]):
                raise ValueError('题目不存在、尚未核验或属于冻结模拟卷')
            snapshot = matches[0]
        with self.factory.begin() as session:
            session.add(ExamSession(id=sid, user_id=self.user_id, subject=subject or None,
                                    chapter=topic_id or chapter or None,
                                    current_question_id=question_id, current_snapshot=snapshot))
        return sid

    def resume(self):
        with self.factory() as session:
            row = session.scalar(select(ExamSession).where(
                ExamSession.user_id == self.user_id, ExamSession.status == 'active'
            ).order_by(ExamSession.started_at.desc()))
            return row.id if row else None

    def _session(self, session, sid):
        row = session.get(ExamSession, sid)
        if not row or row.user_id != self.user_id:
            raise ValueError('诊断记录不存在')
        return row

    def _public(self, question, progress):
        """只把不含答案的字段送到前端，避免作答前泄露标准答案或解析。"""
        allowed = ('id', 'subject', 'topic_ids', 'difficulty', 'question_type', 'stem', 'options',
                   'image', 'images', 'source_type', 'source_reference', 'recommendation_reason',
                   'allowed_symbols','physical_conditions','answer_unit','estimated_minutes','difficulty_source','time_source')
        result = {key: question[key] for key in allowed if key in question}
        names = {t['id']: t['name'] for t in self.repository.topic_tree()}
        result['topic_names'] = [names.get(t, t) for t in question['topic_ids']]
        result['session_progress'] = progress
        return result

    def next(self, session_id):
        """取下一题；同一会话内重复调用返回同一题，保证刷新不会换题。"""
        # Generated foundation exercises use a different parameter variant for
        # remedy/transfer. Reuse persisted generation; no paid model retry.
        with self.factory() as s:
            state = self._session(s, session_id)
            last = s.scalar(select(Attempt).where(Attempt.session_id == session_id).order_by(Attempt.id.desc()))
            gen = last.snapshot.get('generation') if last else None
            needs_variant = not state.current_snapshot and gen and (last.status == 'incorrect' or last.feedback.get('hint_level'))
        if needs_variant:
            qid = self.generate_practice(gen['model'], last.snapshot['topic_ids'][0], gen['variant']+1)
            with self.factory.begin() as s:
                state = self._session(s, session_id)
                if not state.current_snapshot:
                    q = s.get(Question, qid).payload
                    state.current_question_id = qid
                    state.current_snapshot = q | {'recommendation_reason':'前题需补救或借助提示；用新参数独立验证基础定律。'}
        with self.lock, self.factory.begin() as session:
            current = self._session(session, session_id)
            rows = list(session.scalars(select(Attempt).where(
                Attempt.session_id == session_id).order_by(Attempt.id)))
            if current.current_snapshot:
                return self._public(current.current_snapshot, len(rows))
            questions = self.repository.list_questions(subject=current.subject)
            if current.chapter:
                tree = self.repository.topic_tree()
                subset = {current.chapter}
                previous = 0
                while previous != len(subset):
                    previous = len(subset)
                    subset.update(t['id'] for t in tree if t['parent_id'] in subset)
                questions = [q for q in questions if set(q['topic_ids']) & subset]
            records = {m.topic_id: {'estimate': m.estimate, 'attempts': m.attempts}
                       for m in session.scalars(select(MasteryRecord).where(
                           MasteryRecord.user_id == self.user_id))}
            due = {r.topic_id for r in session.scalars(select(ReviewSchedule).where(
                ReviewSchedule.user_id == self.user_id, ReviewSchedule.due_at <= naive_utcnow()))}
            attempts = [{'question_id': a.question_id, 'status': a.status, 'topic_ids': a.snapshot['topic_ids']}
                        for a in rows]
            prerequisites = {t['id']: t['prerequisite_ids'] for t in self.repository.topic_tree()}
            question = select_question(questions, attempts, records, prerequisites, due)
            if not question:
                current.status = 'completed'
                return None
            current.current_question_id = question['id']
            current.current_snapshot = question
            return self._public(question, len(rows))

    def tutor(self, session_id, question_id, text, client=None, full=False):
        from .tutor import respond
        return respond(self, session_id, question_id, text, client, full)

    def tutor_history(self, session_id):
        from .tutor import conversation
        return conversation(self, session_id)

    def generate_practice(self, model, topic_id, variant=0):
        from ..questions.generation import generate
        question = generate(model, topic_id, variant)
        return self.store_generated(question)['id']

    def store_generated(self, question):
        from ..questions.generated_validation import validate_generated
        from ..questions.candidates import MODEL_TOPICS
        if question.get('topic_ids') != [MODEL_TOPICS.get(question.get('generation',{}).get('model'))]:
            raise ValueError('生成题模型与考点映射不一致。')
        result = validate_generated(question)
        if not result['passed']:
            raise ValueError('生成题未通过独立程序校验。')
        if question['topic_ids'] == ['PHY-MECH-ROT-TORQUE'] and not any(t['id']=='PHY-MECH-ROT-TORQUE' for t in self.repository.topic_tree()):
            self.repository.save_topics([{'id':'PHY-MECH-ROT-TORQUE','name':'力矩大小与力臂',
                'parent_id':'PHY-MECH-ROT','prerequisite_ids':['PHY-MECH-DYN-001'],
                'source_references':['定义：力矩为位置矢量与力的叉积；基础诊断节点，非官方大纲条目。']}])
        from ..questions.validator import validate_question
        data=validate_question(question) | {'machine_validated':True,'verified':False,
            'human_verified':False,'source_type':'ai_generated','content_status':'practice_ready','validation':result,
            'generation':question['generation'] | {'status':'machine_validated'}}
        with self.lock, self.factory.begin() as s:
            s.connection().exec_driver_sql('BEGIN IMMEDIATE')
            existing=s.get(Question,data['id'])
            if existing:
                old=existing.payload
                if (existing.version==1 and old.get('machine_validated') and not old.get('verified') and
                    not old.get('human_verified') and not old.get('reported_issue') and not old.get('review_evidence') and
                    old.get('content_status')=='practice_ready' and old.get('source_type')=='ai_generated' and
                    old.get('generation',{}).get('model')==data['generation']['model'] and
                    old.get('generation',{}).get('variant')==data['generation']['variant'] and
                    not validate_generated(old)['passed']):
                    # Correct an untouched program-owned cache definition. IDs
                    # and historic attempt snapshots remain unchanged.
                    existing.payload=data; existing.version+=1
                    return data | {'version':existing.version}
                # A reported or edited cached item is never overwritten by
                # regeneration, even across separate application instances.
                return existing.payload | {'version':existing.version}
            for topic in data['topic_ids']:
                if not s.get(Topic,topic):
                    raise ValueError('生成题所需知识点不存在。')
            s.add(Question(id=data['id'],subject=data['subject'],difficulty=data['difficulty'],
                question_type=data['question_type'],verified=False,version=1,payload=data))
            s.flush()
            for topic in data['topic_ids']:
                s.add(QuestionTopic(question_id=data['id'],topic_id=topic))
            return data | {'version':1}

    def start_route(self, mode, subject=None, chapter=None):
        if mode == '从零开始':
            model = 'born' if subject == 'quantum' else 'newton'
            topic = 'PHY-QM-SPIN-001' if model == 'born' else 'PHY-MECH-DYN-001'
            return self.start(question_id=self.generate_practice(model, topic))
        data = self.dashboard()
        candidates = self.list_questions(subject=subject or None)
        usable_topics = {t for q in candidates if q.get('verified') or q.get('machine_validated') for t in q['topic_ids']}
        if mode == '到期复习':
            due = [r['topic_id'] for r in data['due_reviews'] if r['topic_id'] in usable_topics]
            if not due:
                raise ValueError('当前科目暂无到期复测。可以选择快速诊断。')
            chapter = due[0]
        elif mode == '专项补弱' and not chapter:
            weak = [r['topic_id'] for r in data['weak_topics'] if r['topic_id'] in usable_topics]
            chapter = weak[0] if weak else None
        elif mode == '指定章节' and not chapter:
            raise ValueError('请选择一个章节或知识点。')
        return self.start(subject=subject or None, chapter=chapter or None)

    def hint(self, question_id, session_id=None):
        if session_id:
            return self.tutor(session_id, question_id, '提示一下')['teacher']
        rows = [q for q in self.repository.list_questions() if q['id'] == question_id]
        return rows[0].get('hint', '先列已知量、适用物理定律与边界条件；不要急于代入数值。') if rows else ''

    # ------------------------------------------------------------------ 提交

    def submit(self, session_id, question_id, answer, token):
        """提交一次作答。

        事务与 token 唯一约束共同保证：重复点击提交只会产生一条答题记录。
        """
        from ..diagnosis.math_grader import grade
        if not token or len(token) > 200:
            raise ValueError('需要有效提交标识')
        with self.lock, self.factory.begin() as session:
            # 先占写锁，使跨实例的重复提交也能被 token 唯一约束拦住。
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            prior = session.scalar(select(Attempt).where(
                Attempt.user_id == self.user_id, Attempt.token == token))
            if prior:
                if prior.session_id != session_id or prior.question_id != question_id:
                    raise ValueError('提交标识已用于另一题')
                return prior.feedback
            current = self._session(session, session_id)
            if current.current_question_id != question_id or not current.current_snapshot:
                raise ValueError('请先获取当前题，或本题已提交')
            question = dict(current.current_snapshot)
            live = session.get(Question,question_id)
            options = {key: question[key] for key in
                       ('allowed_symbols', 'positive_symbols', 'assumptions', 'numeric_tolerance', 'expected_unit')
                       if key in question}
            feedback = grade(answer, question['correct_answer'], question['question_type'], options=options)
            from ..questions.eligibility import is_practice_eligible
            if not live or not is_practice_eligible(live.payload) or not is_practice_eligible(question):
                feedback = {'status': 'uncertain', 'explanation': '本题已报告问题或暂停，停止确定性评分。'}
            status = feedback['status']
            category, reason = error_analysis(status, question['question_type'])
            names = {t['id']: t['name'] for t in self.repository.topic_tree()}
            feedback = feedback | {
                'correct_answer': question['correct_answer'],
                'solution': question['solution'],
                'error_category': category,
                'error_analysis': reason,
                'topic_names': [names.get(t, t) for t in question['topic_ids']],
                'mastery': [],
                'hint_level': question.get('hint_level', 0),
                'independent': not bool(question.get('hint_level', 0) or question.get('prior_exposure')),
                'confidence': 'deterministic' if status in ('correct','incorrect') else 'uncertain',
                'elapsed_seconds': max(0, min(1200, (naive_utcnow()-datetime.fromisoformat(question['practice_started_at']).replace(tzinfo=None)).total_seconds())) if question.get('practice_started_at') else 0,
                'timing_source': 'question_open_to_submit_capped_20min' if question.get('practice_started_at') else 'unobserved',
                'delayed_retest': False,
                'remediation_stage': question.get('remediation_stage'),
                'question_attempt_number': 1+session.scalar(select(func.count()).select_from(Attempt).where(Attempt.session_id==session_id,Attempt.question_id==question_id)),
            }
            if status in ('correct', 'incorrect'):
                prior_successes=list(session.scalars(select(Attempt).where(Attempt.user_id==self.user_id,
                    Attempt.status=='correct',Attempt.created_at>=naive_utcnow()-timedelta(days=1))))
                family=question.get('generation',{}).get('model')
                same_day_repeat = status=='correct' and any(not a.feedback.get('hint_level') and
                    (a.question_id==question_id or (family and a.snapshot.get('generation',{}).get('model')==family)) for a in prior_successes)
                feedback['same_day_repeat']=same_day_repeat
                for topic in question['topic_ids']:
                    record = session.get(MasteryRecord, (self.user_id, topic)) or MasteryRecord(
                        user_id=self.user_id, topic_id=topic, attempts=0, correct=0, recent=[])
                    independent = feedback['independent']
                    previous_review = session.get(ReviewSchedule,(self.user_id,topic))
                    delayed = independent and previous_review is not None and previous_review.due_at <= naive_utcnow() and record.last_practiced is not None and record.last_practiced <= naive_utcnow()-timedelta(days=1)
                    feedback['delayed_retest'] = feedback['delayed_retest'] or delayed
                    if status == 'correct' and (not independent or same_day_repeat):
                        # Assistance is not independent mastery evidence.
                        interval, due = 1, naive_utcnow() + timedelta(days=1)
                        if same_day_repeat and independent and previous_review is not None:
                            interval, due = previous_review.interval_days, previous_review.due_at
                    else:
                        interval, due = update_mastery(record, status == 'correct', question['difficulty'],now=naive_utcnow())
                        if status == 'correct' and not delayed:
                            # Same-day success is exploratory evidence, never a
                            # reason to extend the delayed retention interval.
                            interval, due = 3, naive_utcnow()+timedelta(days=3)
                    if previous_review is not None and status=='correct' and not delayed and independent:
                        # Exploratory practice must not postpone a pending
                        # retention test. A genuinely delayed result may move it.
                        interval,due=previous_review.interval_days,previous_review.due_at
                    # This is observed practice time, including assisted work;
                    # it does not imply an increase in independent mastery.
                    record.last_practiced=naive_utcnow()
                    session.add(record)
                    review = session.get(ReviewSchedule, (self.user_id, topic)) or ReviewSchedule(
                        user_id=self.user_id, topic_id=topic)
                    review.due_at = due
                    review.interval_days = interval
                    session.add(review)
                    feedback['mastery'].append({'topic_id': topic, 'estimate': record.estimate,
                                                'attempts': record.attempts, 'due_at': to_iso(due)})
            feedback['evidence_kind'] = ('uncertain' if status=='uncertain' else
                'solution_assisted' if question.get('hint_level')==4 else
                'hint_assisted' if question.get('hint_level') else
                'original_revisit' if question.get('prior_exposure') else
                'same_day_repeat' if feedback.get('same_day_repeat') else
                'delayed_independent' if feedback['delayed_retest'] else
                'independent_transfer' if question.get('remediation_stage')=='verification' else 'independent_attempt')
            session.add(Attempt(user_id=self.user_id, session_id=session_id, question_id=question_id,
                                token=token, answer=answer, snapshot=question, feedback=feedback, status=status))
            current.current_question_id = None
            current.current_snapshot = None
            return feedback

    # ------------------------------------------------------------ 学习记录读取

    def topic_tree(self):
        tree = self.repository.topic_tree()
        with self.factory() as session:
            mastery = {m.topic_id: m.estimate for m in session.scalars(select(MasteryRecord).where(
                MasteryRecord.user_id == self.user_id))}
        return [t | {'mastery': mastery.get(t['id'])} for t in tree]

    def history(self):
        with self.factory() as session:
            return [{'id': r.id, 'subject': r.subject, 'chapter': r.chapter,
                     'started_at': to_iso(r.started_at), 'status': r.status}
                    for r in session.scalars(select(ExamSession).where(
                        ExamSession.user_id == self.user_id).order_by(ExamSession.started_at.desc()))]

    def wrong_answers(self, topic_id=None):
        with self.factory() as session:
            rows = list(session.scalars(select(Attempt).where(
                Attempt.user_id == self.user_id, Attempt.status == 'incorrect').order_by(Attempt.id.desc())))
            return [{'id': a.id, 'question_id': a.question_id, 'answer': a.answer, 'snapshot': a.snapshot,
                     'feedback': a.feedback, 'created_at': to_iso(a.created_at),
                     'topic_ids': a.snapshot['topic_ids'], 'stem': a.snapshot['stem']}
                    for a in rows if not topic_id or topic_id in a.snapshot['topic_ids']]

    def report(self, session_id):
        with self.factory() as session:
            self._session(session, session_id)
            rows = list(session.scalars(select(Attempt).where(Attempt.session_id == session_id)))
        certain = [a for a in rows if a.status != 'uncertain']
        return {
            'session_id': session_id,
            'attempts': len(rows),
            'correct': sum(a.status == 'correct' for a in rows),
            'uncertain': len(rows) - len(certain),
            'accuracy': sum(a.status == 'correct' for a in certain) / len(certain) if certain else None,
            'topics': list({t for a in rows for t in a.snapshot['topic_ids']}),
            'independent_attempts': sum(a.feedback.get('independent',not a.feedback.get('hint_level')) for a in rows),
            'independent_correct': sum(a.status == 'correct' and a.feedback.get('independent',not a.feedback.get('hint_level')) for a in rows),
            'independent_accuracy': sum(a.status=='correct' for a in certain if a.feedback.get('independent',not a.feedback.get('hint_level'))) / len([a for a in certain if a.feedback.get('independent',not a.feedback.get('hint_level'))]) if any(a.feedback.get('independent',not a.feedback.get('hint_level')) for a in certain) else None,
            'delayed_independent_count': sum(bool(a.feedback.get('delayed_retest')) for a in rows),
            'delayed_independent_correct': sum(a.status=='correct' and bool(a.feedback.get('delayed_retest')) for a in rows),
            'remediation_attempts': sum(a.feedback.get('remediation_stage')=='remediation' for a in rows),
            'independent_transfer_correct': sum(a.status=='correct' and not a.feedback.get('hint_level') and a.feedback.get('remediation_stage')=='verification' for a in rows),
            'needs_independent_retest': sorted({t for a in rows if a.status != 'correct' or a.feedback.get('hint_level') for t in a.snapshot['topic_ids']}),
            'next_suggestion': '先完成到期无提示复测；错误后用基础变式检验，再返回原考点。',
            'coverage_notice': '仅反映本次有限样本，题库覆盖不足或未知考点不可据此认定掌握。',
        }

    def dashboard(self):
        now = naive_utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        names = {t['id']: t['name'] for t in self.repository.topic_tree()}
        with self.factory() as session:
            attempts = list(session.scalars(select(Attempt).where(Attempt.user_id == self.user_id)))
            records = list(session.scalars(select(MasteryRecord).where(
                MasteryRecord.user_id == self.user_id)))
            reviews = list(session.scalars(select(ReviewSchedule).where(
                ReviewSchedule.user_id == self.user_id, ReviewSchedule.due_at <= now)))
        recent = [a for a in attempts if a.created_at >= today - timedelta(days=6) and a.status != 'uncertain']
        mastery = [{'topic_id': m.topic_id, 'name': names.get(m.topic_id, m.topic_id),
                    'estimate': m.estimate, 'attempts': m.attempts, 'correct': m.correct,
                    'recent_accuracy': sum(r['correct'] for r in m.recent) / len(m.recent) if m.recent else None,
                    'last_practiced': to_iso(m.last_practiced)} for m in records]
        return {
            'today_count': sum(a.created_at >= today for a in attempts),
            'seven_day_accuracy': sum(a.status == 'correct' for a in recent) / len(recent) if recent else None,
            'mastery': mastery,
            'weak_topics': sorted(mastery, key=lambda x: x['estimate'] if x['estimate'] is not None else -1)[:8],
            'due_reviews': [{'topic_id': r.topic_id, 'name': names.get(r.topic_id, r.topic_id),
                             'due_at': to_iso(r.due_at)} for r in reviews],
            'recent_sessions': self.history()[:5],
            'daily_counts': [{'date': (today - timedelta(days=i)).date().isoformat(),
                              'count': sum(a.created_at.date() == (today - timedelta(days=i)).date()
                                           for a in attempts)} for i in range(6, -1, -1)],
        }

    # -------------------------------------------------------------- 题库与知识树

    def list_questions(self, **kwargs):
        return self.repository.list_questions(**kwargs)

    def save_question(self, data):
        return self.repository.save_questions([data])

    def review_question(self, question_id, verified, evidence):
        return self.repository.review_question(question_id, verified, evidence)

    def delete_question(self, question_id):
        return self.repository.delete_question(question_id)

    def save_topic(self, data):
        return self.repository.save_topics([data])

    def delete_topic(self, topic_id):
        return self.repository.delete_topic(topic_id)

    def import_questions(self, path):
        return self.repository.import_questions(path)

    def export_questions(self, path):
        return self.repository.export_questions(path)

    def mark_question(self, question_id):
        with self.factory.begin() as session:
            if not session.get(Question, question_id):
                raise ValueError('题目不存在')
            row = session.get(QuestionMark, (self.user_id, question_id))
            if row:
                session.delete(row)
                return '已取消题目标记'
            session.add(QuestionMark(user_id=self.user_id, question_id=question_id))
            return '已标记，重启后仍保留'

    def import_topics(self, path):
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == '.json':
            items = json.loads(path.read_text(encoding='utf-8-sig'))
        elif suffix in ('.yaml', '.yml'):
            import yaml
            items = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
        elif suffix == '.csv':
            with path.open(encoding='utf-8-sig', newline='') as handle:
                items = list(csv.DictReader(handle))
            for row in items:
                row['parent_id'] = row.get('parent_id') or None
                row['difficulty'] = int(row.get('difficulty') or 1)
                for key in ('prerequisite_ids', 'source_references'):
                    row[key] = json.loads(row.get(key) or '[]')
        else:
            raise ValueError('知识树支持 JSON / YAML / CSV')
        if isinstance(items, dict):
            items = items.get('topics', [])
        return self.repository.save_topics(items)

    def export_topics(self, path):
        path = Path(path)
        path.write_text(json.dumps(self.repository.topic_tree(), ensure_ascii=False, indent=2), encoding='utf-8')
        return str(path)

    # ------------------------------------------------------------ 备份与恢复

    def backup(self, path):
        path = Path(path).resolve()
        if path == self.path:
            raise ValueError('备份不能覆盖当前数据库')
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, sqlite3.connect(self.path) as source, sqlite3.connect(path) as target:
            source.backup(target)
        return str(path)

    def restore(self, path):
        path = Path(path).resolve()
        if not path.is_file() or path == self.path:
            raise ValueError('恢复文件无效')
        with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as source:
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('备份损坏')
            tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'attempts', 'topics', 'questions', 'mastery_records', 'schema_migrations'} <= tables:
                raise ValueError('不是 PhysicsPrep 备份')
            with self.lock:
                self.engine.dispose()
                with sqlite3.connect(self.path) as target:
                    source.backup(target)
                self.engine, self.factory = initialize_database(self.path)
                self.repository = Repository(self.factory)
        return str(self.path)


StudyService = LearningService
