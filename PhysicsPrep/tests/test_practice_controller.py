from pathlib import Path
import pytest
from sqlalchemy import select, text
from physics_prep.services.learning import LearningService
from physics_prep.services.practice import PracticeSessionController
from physics_prep.database.models import Attempt, PracticeState, ExamSession

@pytest.fixture
def service(tmp_path):
    return LearningService(tmp_path/'practice.sqlite3',Path(__file__).parents[1]/'data')

def answer(service,q):
    return next(x for x in service.list_questions() if x['id']==q['id'])['correct_answer']

def wrong_answer(q):
    return ['Z'] if q['question_type']=='multiple_choice' else 'Z' if q['question_type']=='single_choice' else '0'

def test_start_feedback_next_and_duplicate(service):
    c=PracticeSessionController(service)
    v=c.start('general'); sid=v['session_id']; q=v['question']
    assert q and q['subject']!='quantum' and 'correct_answer' not in q
    v=c.submit(sid,q['id'],answer(service,q),'once')
    assert v['state']['phase']=='FEEDBACK' and v['question']['id']==q['id']
    assert v['next_reason']
    assert c.submit(sid,q['id'],answer(service,q),'once')['state']['attempts']==1
    n=c.next(sid); assert n['question']['id']!=q['id']
    assert c.next(sid)['question']['id']==n['question']['id']

def test_torque_remediation_verification_return(service):
    c=PracticeSessionController(service)
    v=c.start('general','chapter','PHY-MECH-ROT-003'); sid=v['session_id']; q=v['question']
    v=c.submit(sid,q['id'],wrong_answer(q),'wrong')
    assert v['remedy']['target']=='PHY-MECH-ROT-TORQUE'
    v=c.next(sid); assert v['state']['phase']=='REMEDIATION'
    first=v['question']; assert first['topic_ids']==['PHY-MECH-ROT-TORQUE']
    c.submit(sid,first['id'],answer(service,first),'remedy')
    second=c.next(sid); assert second['state']['phase']=='VERIFICATION'
    assert second['question']['stem']!=first['stem']
    c.submit(sid,second['question']['id'],answer(service,second['question']),'verify')
    returned=c.next(sid); assert returned['question']['id']==q['id']
    assert returned['state']['hint_level']==0
    assert not returned['state']['independent']
    final=c.submit(sid,q['id'],answer(service,q),'returned')
    assert not final['feedback']['independent'] and final['feedback']['evidence_kind']=='original_revisit'
    assert not final['remedy']

def test_hints_uncertainty_and_full_solution(service):
    c=PracticeSessionController(service)
    v=c.start('general','chapter','PHY-MECH-DYN-001'); sid=v['session_id']; q=v['question']
    for _ in range(4): c.hint(sid,q['id'])
    assert c.view(sid)['state']['hint_level']==3
    assert c.hint(sid,q['id'],full=True)['hint_level']==4
    v=c.submit(sid,q['id'],answer(service,q),'helped')
    assert v['feedback']['status']=='correct' and not v['feedback']['independent']
    assert v['summary']['independent_correct']==0

def test_twenty_questions_restart_and_end(service):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; ids=[]
    for i in range(20):
        q=v['question']; ids.append(q['id'])
        c.submit(sid,q['id'],answer(service,q),f'answer-{i}')
        v=c.next(sid)
    assert len(set(ids))==20
    service.engine.dispose()
    resumed=PracticeSessionController(LearningService(service.path))
    r=resumed.resume()
    assert r['summary']['attempts']==20 and r['question']['id']==v['question']['id']
    assert r['summary']['independent_correct']==20
    done=resumed.finish(sid)
    assert done['state']['phase']=='SAVED' and resumed.resume() is None

def test_recovery_after_grade_before_checkpoint(service):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    service.submit(sid,q['id'],answer(service,q),'crash-window')
    recovered=PracticeSessionController(LearningService(service.path)).view(sid)
    assert recovered['state']['attempts']==1
    assert c.view(sid)['state']['attempts']==1

def test_help_input_is_not_a_grade(service):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    guided=c.submit(sid,q['id'],'完全没思路','help-token')
    assert guided['guidance'] and guided['summary']['attempts']==0
    assert guided['state']['hint_level']>0

def test_budgeted_remediation_no_recursion_loop(service):
    c=PracticeSessionController(service); v=c.start('general','chapter','PHY-MECH-ROT-003'); sid=v['session_id']
    for i in range(5):
        q=v['question']; c.submit(sid,q['id'],wrong_answer(q),f'failure-{i}')
        v=c.next(sid)
        assert v['state']['attempts']==i+1
        assert not v['remedy'] or v['remedy']['depth']<=3

def test_migration_backup_restore_preserves_state(service,tmp_path):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']
    backup=tmp_path/'backup.sqlite3'; service.backup(backup)
    c.hint(sid,v['question']['id'])
    service.restore(backup)
    assert c.view(sid)['state']['hint_level']==0
    with service.engine.connect() as conn:
        assert conn.execute(text('SELECT max(version) FROM schema_migrations')).scalar()==4

def test_generation_with_broken_model_falls_back(service):
    class Broken:
        def ask(self,*args,**kwargs): raise TimeoutError()
    c=PracticeSessionController(service,lambda:Broken())
    v=c.start('general','chapter','PHY-MECH-ROT-TORQUE')
    assert v['question'] and v['state']['generation_calls']==1
    q=v['question']; assert 'GEN-' in q['id']
    assert service.list_questions(search=q['id'])[0]['machine_validated']

def test_ui_controller_chain(service):
    from physics_prep.ui.application import build_app
    app=build_app(service)
    fns={f.fn.__name__:f.fn for f in app.fns.values() if f.fn}
    v=fns['practice_start']('quantum','adaptive',''); sid,qid,token=v[:3]
    q=next(q for q in service.list_questions() if q['id']==qid)
    done=fns['practice_submit'](sid,qid,token,None,[],q['correct_answer'])
    assert done[10]['interactive'] is False and done[12]['interactive'] is True
    nxt=fns['practice_next'](sid); assert nxt[1]!=qid

def test_process_assessment_remains_uncertain_and_cached(service):
    service.save_topic({'id':'process','name':'过程评估测试','parent_id':'PHY'})
    service.save_question({'id':'OPEN-TEST','subject':'mechanics','topic_ids':['process'],
        'difficulty':1,'question_type':'derivation','stem':'说明受力分析步骤。','correct_answer':'先选对象',
        'solution':'选择对象并列出全部外力，然后写合力方程。','source_type':'original','verified':True})
    class Teacher:
        calls=0
        def ask(self,*args,**kwargs):
            self.calls+=1
            return {'mode':'online','text':'{"assessment":"partial","recognized_steps":["已选对象"],"possible_issues":["可能遗漏外力"],"next_action":"列出对象受到的全部力。"}'}
    teacher=Teacher(); c=PracticeSessionController(service,lambda:teacher)
    v=c.start('general','chapter','process'); sid=v['session_id']; q=v['question']
    v=c.submit(sid,q['id'],'我先选研究对象，再列方程。','process-once')
    assert v['feedback']['status']=='uncertain' and v['feedback']['process_assessment']['assessment']=='partial'
    c.submit(sid,q['id'],'same','process-once')
    assert teacher.calls==1 and not service.dashboard()['mastery']

def test_retry_after_solution_is_assisted_and_stable(service):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    c.submit(sid,q['id'],wrong_answer(q),'retry-wrong')
    c.hint(sid,q['id'],full=True)
    c.try_again(sid)
    v=c.submit(sid,q['id'],answer(service,q),'retry-correct')
    assert v['feedback']['question_attempt_number']==2
    assert v['feedback']['evidence_kind']=='solution_assisted'
    assert v['summary']['independent_correct']==0

def test_student_error_category_persists(service):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    c.submit(sid,q['id'],wrong_answer(q),'label-wrong')
    v=c.record_error(sid,'符号或方向错误')
    assert v['state']['last_feedback']['error_source']=='student'
    assert PracticeSessionController(LearningService(service.path)).view(sid)['state']['last_feedback']['error_category']=='符号或方向错误'

def test_delayed_retest_uses_clock_control_not_fake_learning_claim(service,monkeypatch):
    from datetime import timedelta
    from physics_prep.services import learning
    c=PracticeSessionController(service); v=c.start(); q=v['question']; sid=v['session_id']
    first=c.submit(sid,q['id'],answer(service,q),'day0')
    assert not first['feedback']['delayed_retest']
    future=learning.naive_utcnow()+timedelta(days=4)
    monkeypatch.setattr(learning,'naive_utcnow',lambda:future)
    other=service.start(question_id=q['id']); service.next(other)
    delayed=service.submit(other,q['id'],answer(service,q),'controlled-day4')
    assert delayed['delayed_retest'] and delayed['evidence_kind']=='delayed_independent'

def test_reported_current_question_can_be_skipped(service):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    c.hint(sid,q['id'],text='题目有误：条件不清楚')
    next_view=c.next(sid)
    assert next_view['question']['id']!=q['id']
    assert next_view['summary']['attempts']==0

def test_generated_topic_mapping_is_enforced(service):
    from physics_prep.questions.generation import generate
    with pytest.raises(ValueError,match='映射'):
        service.store_generated(generate('newton','PHY-QM-SPIN-001'))

def test_two_services_share_lock_and_state_cas(service):
    first=PracticeSessionController(service); v=first.start(); sid=v['session_id']
    second=PracticeSessionController(LearningService(service.path))
    assert first.service.lock is second.service.lock
    stale=first._load(sid)
    fresh=second._load(sid); fresh['notice']='second writer'; second._save(sid,fresh)
    with pytest.raises(ValueError,match='其他窗口'):
        first._save(sid,stale)
    assert first.view(sid)['state']['notice']=='second writer'

def test_concurrent_next_and_duplicate_submission(service):
    from concurrent.futures import ThreadPoolExecutor
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    other=PracticeSessionController(LearningService(service.path))
    with ThreadPoolExecutor(2) as pool:
        tasks=[pool.submit(x.submit,sid,q['id'],answer(service,q),'parallel-token') for x in (c,other)]
        views=[task.result() for task in tasks]
    assert all(x['summary']['attempts']==1 for x in views)
    with ThreadPoolExecutor(2) as pool:
        tasks=[pool.submit(x.next,sid) for x in (c,other)]
        views=[task.result() for task in tasks]
    assert views[0]['question']['id']==views[1]['question']['id']

@pytest.mark.parametrize('revocation', ['delete','unverified','frozen','out_of_scope'])
def test_revocation_after_snapshot_stops_grading(service,revocation):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    if revocation=='delete': service.delete_question(q['id'])
    else:
        raw=next(x for x in service.list_questions() if x['id']==q['id'])
        if revocation=='unverified': raw['verified']=False
        elif revocation=='frozen': raw['frozen']=True
        else: raw['content_status']='out_of_scope'
        service.save_question(raw)
    result=c.submit(sid,q['id'],'0','revoked')
    assert result['feedback']['status']=='uncertain' and not service.dashboard()['mastery']

def test_hint_level_cannot_decrease_after_solution(service):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    c.hint(sid,q['id'],full=True)
    c.hint(sid,q['id'])
    assert c.view(sid)['state']['hint_level']==4

def test_same_day_generated_family_does_not_inflate_mastery(service):
    first=service.generate_practice('newton','PHY-MECH-DYN-001',0)
    sid=service.start(question_id=first); q=service.next(sid)
    service.submit(sid,first,'3','family0')
    before=next(x for x in service.dashboard()['mastery'] if x['topic_id']=='PHY-MECH-DYN-001')
    second=service.generate_practice('newton','PHY-MECH-DYN-001',1)
    sid2=service.start(question_id=second); service.next(sid2)
    result=service.submit(sid2,second,'7/3','family1')
    after=next(x for x in service.dashboard()['mastery'] if x['topic_id']=='PHY-MECH-DYN-001')
    assert result['same_day_repeat'] and before['estimate']==after['estimate']
    assert before['attempts']==after['attempts']

def test_activation_checkpoint_crash_recovers_active_card(service):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    c.submit(sid,q['id'],answer(service,q),'activation-old')
    prepared=c._load(sid)['prepared']
    with service.factory.begin() as s:
        row=s.get(ExamSession,sid)
        row.current_question_id=prepared['id']; row.current_snapshot=prepared | {'hint_level':0}
    recovered=PracticeSessionController(LearningService(service.path)).resume()
    assert recovered['question']['id']==prepared['id']
    assert recovered['state']['phase']=='QUESTION'
    assert recovered['summary']['attempts']==1

def test_assisted_work_can_be_followed_by_delayed_independent_retest(service,monkeypatch):
    from datetime import timedelta
    from physics_prep.services import learning
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    c.hint(sid,q['id'])
    c.submit(sid,q['id'],answer(service,q),'hint-day0')
    future=learning.naive_utcnow()+timedelta(days=2)
    monkeypatch.setattr(learning,'naive_utcnow',lambda:future)
    other=service.start(question_id=q['id']); service.next(other)
    result=service.submit(other,q['id'],answer(service,q),'hint-day2')
    assert result['delayed_retest'] and result['independent']

def test_unable_to_start_goes_to_foundation_without_fake_grade(service):
    c=PracticeSessionController(service); v=c.start('general','chapter','PHY-MECH-ROT-003'); sid=v['session_id']
    remedied=c.remediate_now(sid)
    assert remedied['question']['topic_ids']==['PHY-MECH-ROT-TORQUE']
    assert remedied['state']['unable_to_start_count']==1
    assert remedied['summary']['attempts']==0 and not service.dashboard()['mastery']

def test_uncovered_chapter_falls_back_without_claiming_coverage(service):
    c=PracticeSessionController(service)
    v=c.start('quantum','chapter','PHY-QM-APPROX-001')
    assert v['question'] and v['question']['subject']=='quantum'
    assert 'PHY-QM-APPROX-001' in v['summary']['coverage_gaps']
    assert not service.dashboard()['mastery']

def test_real_pulley_model_demotes_to_torque_then_returns(service):
    c=PracticeSessionController(service)
    v=c.start('general','chapter','PHY-MECH-ROT-PULLEY'); sid=v['session_id']; original=v['question']
    assert original['difficulty']==3 and '轻绳' in original['stem']
    c.submit(sid,original['id'],'0','pulley-wrong')
    v=c.next(sid); assert v['question']['topic_ids']==['PHY-MECH-ROT-TORQUE']
    c.submit(sid,v['question']['id'],answer(service,v['question']),'pulley-torque')
    v=c.next(sid); assert v['state']['phase']=='VERIFICATION'
    c.submit(sid,v['question']['id'],answer(service,v['question']),'pulley-transfer')
    v=c.next(sid); assert v['question']['id']==original['id'] and not v['state']['independent']

def test_answer_in_teacher_panel_syncs_feedback_and_next(service):
    c=PracticeSessionController(service); v=c.start(); sid=v['session_id']; q=v['question']
    response=c.hint(sid,q['id'],text='答案：'+str(answer(service,q)))
    assert response['submitted']
    assert c.view(sid)['state']['phase']=='FEEDBACK'
    assert c.next(sid)['question']['id']!=q['id']

def test_untouched_invalid_machine_cache_refresh_keeps_id_and_history(service):
    from physics_prep.questions.generation import generate
    q=generate('newton','PHY-MECH-DYN-001',0)
    stored=service.store_generated(q)
    with service.factory.begin() as s:
        from physics_prep.database.models import Question
        row=s.get(Question,q['id']); row.payload=row.payload | {'solution':'obsolete program explanation'}
    refreshed=service.store_generated(q)
    assert refreshed['id']==stored['id'] and refreshed['version']==2
    assert refreshed['solution']==q['solution'] and refreshed['machine_validated']
