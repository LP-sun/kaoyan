import json
import pytest
from sqlalchemy import select, text
from physics_prep.services.learning import LearningService
from physics_prep.database.models import Attempt
from physics_prep.database.migrations import MIGRATIONS, current_version

@pytest.fixture
def service(tmp_path):
    service=LearningService(tmp_path/'study.sqlite')
    service.repository.save_topics([{'id':'root','name':'物理'},{'id':'kin','name':'运动学','parent_id':'root'},{'id':'roll','name':'滚动','parent_id':'root','prerequisite_ids':['kin']}])
    service.repository.save_questions([
        {'id':str(i),'subject':'mechanics','topic_ids':['kin' if i<2 else 'roll'],'difficulty':1 if i<2 else 2,'question_type':'single_choice','stem':f'原创测试题{i}','options':['正确选项','错误选项'],'correct_answer':'A','solution':'测试选择规则说明','source_type':'original','verified':True}
        for i in range(4)
    ])
    return service

def test_repeatable_migration_and_foreign_keys(service):
    second=LearningService(service.path)
    assert len(second.list_questions())==4
    with second.engine.connect() as c:
        assert c.execute(text('PRAGMA foreign_keys')).scalar()==1
        assert c.execute(text('PRAGMA journal_mode')).scalar()=='wal'
        # 迁移是版本化列表：全部版本都被记录，且重复启动不会重复应用。
        assert c.execute(text('SELECT count(*) FROM schema_migrations')).scalar()==len(MIGRATIONS)
        assert c.execute(text('SELECT max(version) FROM schema_migrations')).scalar()==len(MIGRATIONS)
    assert current_version(second.engine)==len(MIGRATIONS)
    third=LearningService(service.path)
    assert current_version(third.engine)==len(MIGRATIONS)
    assert len(third.list_questions())==4

def test_public_snapshot_and_idempotency(service):
    sid=service.start('mechanics'); q=service.next(sid)
    assert 'correct_answer' not in q and 'solution' not in q
    assert service.next(sid)==q
    data=service.list_questions(search=q['id'])[0]
    data['correct_answer']='B'; service.save_question(data)
    result=service.submit(sid,q['id'],'A','once')
    assert result['status']=='correct' and result['correct_answer']=='A'
    assert service.submit(sid,q['id'],'B','once')==result
    with service.factory() as s: assert len(list(s.scalars(select(Attempt))))==1
    assert service.dashboard()['mastery'][0]['estimate']<.8
    with pytest.raises(ValueError): service.submit(sid,q['id'],'A','other-token')

def test_error_remedy_and_persistence(service):
    sid=service.start('mechanics',topic_id='roll'); q=service.next(sid)
    result=service.submit(sid,q['id'],'B','error')
    assert result['status']=='incorrect'
    assert service.wrong_answers()[0]['answer']=='B'
    assert service.next(sid)['id']!=q['id']
    reopened=LearningService(service.path)
    assert reopened.resume()==sid and len(reopened.wrong_answers())==1
    assert reopened.report(sid)['accuracy']==0

def test_import_export_atomic_and_cycles(service,tmp_path):
    path=tmp_path/'questions.csv'; service.export_questions(path)
    assert service.import_questions(path)==4
    with pytest.raises(ValueError): service.save_topic({'id':'kin','name':'bad','parent_id':'roll','prerequisite_ids':['roll']})
    assert next(t for t in service.topic_tree() if t['id']=='kin')['parent_id']=='root'
    bad=service.list_questions()[0] | {'id':'new','topic_ids':['missing']}
    with pytest.raises(ValueError): service.repository.save_questions([service.list_questions()[0],bad])
    assert not service.list_questions(search='new')

def test_backup_restore(service,tmp_path):
    sid=service.start(); q=service.next(sid); service.submit(sid,q['id'],'B','x')
    backup=tmp_path/'backup.sqlite'; service.backup(backup)
    q=service.next(sid); service.submit(sid,q['id'],'A','y')
    service.restore(backup)
    assert service.report(sid)['attempts']==1

def test_ai_unverified_and_frozen_excluded(service):
    for q in service.list_questions():
        q['source_type']='ai_generated'; q['verified']=False; service.save_question(q)
    sid=service.start(); assert service.next(sid) is None

def test_selector_remedy_coverage_and_no_loop():
    from physics_prep.diagnosis.selector import select_question
    questions=[{'id':'roll','topic_ids':['roll'],'difficulty':2,'verified':True,'source_type':'original'}, {'id':'pre','topic_ids':['kin'],'difficulty':1,'verified':True,'source_type':'original'}, {'id':'other','topic_ids':['thermal'],'difficulty':1,'verified':True,'source_type':'original'}]
    history=[{'question_id':'roll','status':'incorrect','topic_ids':['roll']}]
    chosen=select_question(questions,history,{'roll':{'estimate':.25}},{'roll':['kin']})
    assert chosen['id']=='pre'
    assert '补救' in chosen['recommendation_reason']
    questions.append({'id':'roll2','topic_ids':['roll'],'difficulty':1,'verified':True,'source_type':'original'})
    history*=3
    chosen=select_question(questions,history,{'roll':{'estimate':.1}},{'roll':[]})
    assert chosen['id']!='roll2'

def test_ai_review_mark_and_topic_import(service,tmp_path):
    data=service.list_questions()[0] | {'source_type':'ai_generated','verified':True}
    service.save_question(data)
    assert not service.list_questions(search=data['id'])[0]['verified']
    service.review_question(data['id'],True,'独立验证选项与唯一性')
    assert service.list_questions(search=data['id'])[0]['verified']
    assert '已标记' in service.mark_question(data['id'])
    assert '取消' in LearningService(service.path).mark_question(data['id'])
    path=tmp_path/'topics.json'; service.export_topics(path)
    assert service.import_topics(path)==3
