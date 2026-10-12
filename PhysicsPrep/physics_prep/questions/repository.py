import csv
import json
from pathlib import Path
from sqlalchemy import select, delete
from ..database.models import Topic, TopicPrerequisite, Question, QuestionTopic
from .validator import validate_question

class Repository:
    def __init__(self, factory):
        self.factory = factory

    def save_topics(self, items):
        with self.factory.begin() as s:
            s.connection().exec_driver_sql('BEGIN IMMEDIATE')
            existing = {t.id: {'id':t.id,'name':t.name,'parent_id':t.parent_id,'difficulty':t.difficulty,'source_references':t.source_references,'prerequisite_ids':[]} for t in s.scalars(select(Topic))}
            for edge in s.scalars(select(TopicPrerequisite)):
                existing[edge.topic_id]['prerequisite_ids'].append(edge.prerequisite_id)
            for data in items:
                old = existing.get(data['id'], {})
                existing[data['id']] = old | data
            def visit(node, stack, done, mode):
                if node in stack: raise ValueError('知识图存在循环')
                if node in done: return
                if node not in existing: raise ValueError('不存在的知识点: '+node)
                row = existing[node]
                edges = ([row.get('parent_id')] if mode=='parent' and row.get('parent_id') else row.get('prerequisite_ids',[]) if mode=='prerequisite' else [])
                for nxt in edges: visit(nxt, stack | {node}, done, mode)
                done.add(node)
            for mode in ('parent','prerequisite'):
                done=set()
                for key in existing: visit(key,set(),done,mode)
            # Parent references require topological insertion under SQLite foreign keys.
            pending = [existing[data['id']] for data in items]
            while pending:
                progressed=False
                for data in pending[:]:
                    parent=data.get('parent_id')
                    if parent and not s.get(Topic,parent): continue
                    t=s.get(Topic,data['id']) or Topic(id=data['id'])
                    t.name=data['name']; t.parent_id=parent
                    t.difficulty=data.get('difficulty',1); t.source_references=data.get('source_references',[])
                    s.add(t); s.flush(); pending.remove(data); progressed=True
                if not progressed: raise ValueError('知识点父节点未找到')
            for data in items:
                s.execute(delete(TopicPrerequisite).where(TopicPrerequisite.topic_id==data['id']))
                for pre in existing[data['id']].get('prerequisite_ids',[]):
                    s.add(TopicPrerequisite(topic_id=data['id'], prerequisite_id=pre))
        return len(items)

    def topic_tree(self):
        with self.factory() as s:
            edges=list(s.scalars(select(TopicPrerequisite)))
            return [{'id':t.id,'name':t.name,'parent_id':t.parent_id,'difficulty':t.difficulty,'source_references':t.source_references,'prerequisite_ids':[e.prerequisite_id for e in edges if e.topic_id==t.id]} for t in s.scalars(select(Topic))]

    def save_questions(self, items, allow_ai_verification=False):
        values=[validate_question(x) for x in items]
        for data in values:
            # Client-supplied validation flags are not executable evidence.
            data['machine_validated'] = False
            if data['source_type']=='ai_generated' and not allow_ai_verification:
                data['verified']=False
                data['human_verified']=False
        if len({q['id'] for q in values})!=len(values): raise ValueError('导入含重复题目 ID')
        with self.factory.begin() as s:
            s.connection().exec_driver_sql('BEGIN IMMEDIATE')
            for data in values:
                for topic in data['topic_ids']:
                    if not s.get(Topic,topic): raise ValueError('不存在的知识点: '+topic)
                row=s.get(Question,data['id'])
                if row:
                    row.version += 1
                    s.execute(delete(QuestionTopic).where(QuestionTopic.question_id==row.id))
                else: row=Question(id=data['id'],version=1)
                for field in ('subject','difficulty','question_type','verified'): setattr(row,field,data[field])
                row.payload=data; s.add(row); s.flush()
                for topic in data['topic_ids']: s.add(QuestionTopic(question_id=row.id,topic_id=topic))
        return len(values)

    def review_question(self, question_id, verified, evidence):
        if not str(evidence).strip(): raise ValueError('审核需明确记录验证依据')
        with self.factory.begin() as s:
            q=s.get(Question,question_id)
            if not q: raise ValueError('题目不存在')
            q.verified=bool(verified)
            q.payload=q.payload | {'verified':bool(verified),'human_verified':bool(verified),
                'content_status':'practice_ready' if verified else 'needs_review', 'review_evidence':str(evidence)}
            q.version+=1
        return question_id

    def list_questions(self, subject=None, topic_id=None, difficulty=None, search=None):
        with self.factory() as s:
            rows=[q.payload | {'version':q.version} for q in s.scalars(select(Question))]
        return [q for q in rows if (not subject or q['subject']==subject) and (not topic_id or topic_id in q['topic_ids']) and (not difficulty or q['difficulty']==int(difficulty)) and (not search or search.lower() in (q['id']+' '+q['stem']).lower())]

    def import_questions(self, path):
        path=Path(path)
        if path.suffix.lower()=='.json':
            items=json.loads(path.read_text(encoding='utf-8-sig'))
            if isinstance(items,dict) and 'statement' in items and 'review' in items:
                from .importer import adapt_writing_record
                items=[adapt_writing_record(items)]
            if isinstance(items,dict): items=items.get('questions',[])
        elif path.suffix.lower()=='.csv':
            with path.open(encoding='utf-8-sig',newline='') as f: items=list(csv.DictReader(f))
            for row in items:
                for key in ('topic_ids','options','correct_answer','source_reference','allowed_symbols','assumptions'):
                    if key in row and row[key]:
                        try: row[key]=json.loads(row[key])
                        except json.JSONDecodeError:
                            if key in ('topic_ids','options'): raise ValueError(key+' 必须为 JSON 数组')
                row['verified']=str(row.get('verified','false')).lower() in ('true','1')
                row['difficulty']=int(row['difficulty'])
        else: raise ValueError('只支持 JSON / CSV')
        return self.save_questions(items)

    def export_questions(self, path):
        path=Path(path); rows=self.list_questions()
        if path.suffix.lower()=='.csv':
            keys=sorted(set().union(*(q.keys() for q in rows)))
            with path.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=keys); w.writeheader()
                w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) or k=='correct_answer' else v for k,v in q.items()} for q in rows)
        else: path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        return str(path)

    def delete_topic(self, topic_id):
        with self.factory.begin() as s:
            row=s.get(Topic,topic_id)
            if row: s.delete(row)

    def delete_question(self, question_id):
        with self.factory.begin() as s:
            s.execute(delete(QuestionTopic).where(QuestionTopic.question_id==question_id))
            row=s.get(Question,question_id)
            if row: s.delete(row)
