from pathlib import Path
import pytest
from physics_prep.services.learning import LearningService
from physics_prep.questions.generation import generate

@pytest.fixture
def service(tmp_path):
    return LearningService(tmp_path/'tutor.sqlite3', Path(__file__).parents[1]/'data')

def begin(service):
    qid = service.generate_practice('newton','PHY-MECH-DYN-001')
    sid = service.start(question_id=qid)
    return sid, service.next(sid)

def test_zero_basics_hints_and_independent_retest(service):
    sid, q = begin(service)
    for text in ('我不会','从最基础讲起','提示一下'):
        service.tutor(sid,q['id'],text)
    service.tutor(sid,q['id'],'懂了')
    assert not service.dashboard()['mastery']
    fb = service.submit(sid,q['id'],'3','a')
    assert fb['status']=='correct' and not fb['independent']
    assert fb['mastery'][0]['attempts']==0
    assert service.next(sid)['id']!=q['id']

def test_wrong_remedy_transfer_and_restart(service):
    sid,q = begin(service)
    service.tutor(sid,q['id'],'答案：0')
    second = service.next(sid)
    assert second['id'] != q['id']
    service.tutor(sid,second['id'],'F=ma')
    resumed = LearningService(service.path)
    assert resumed.resume()==sid
    assert resumed.next(sid)['id']==second['id']
    assert resumed.tutor_history(sid)[-1]['kind']=='equation'
    fb = resumed.submit(sid,second['id'], '7/3','b')
    assert fb['status']=='correct' and fb['hint_level']>0

def test_failure_preserves_question_and_retry(service):
    class Fails:
        def ask(self,*args,**kwargs): raise TimeoutError()
    sid,q = begin(service)
    turn = service.tutor(sid,q['id'],'看不懂题目',Fails())
    assert turn['error']=='TimeoutError'
    assert service.next(sid)['id']==q['id']
    assert len(service.tutor_history(sid))==1
    service.tutor(sid,q['id'],'提示一下')
    assert len(service.tutor_history(sid))==2

def test_report_stops_grading(service):
    sid,q = begin(service)
    service.tutor(sid,q['id'],'题目有误')
    assert service.submit(sid,q['id'],'3','c')['status']=='uncertain'
    assert not service.list_questions(search=q['id'])[0]['machine_validated']

def test_full_solution_and_generation_cache(service):
    sid,q = begin(service)
    turn = service.tutor(sid,q['id'],'完整解析')
    assert '标准答案' in turn['teacher']
    old = service.list_questions(search=q['id'])[0]['version']
    service.generate_practice('newton','PHY-MECH-DYN-001')
    assert service.list_questions(search=q['id'])[0]['version']==old

def test_online_context_and_ui_call_chain(service):
    from physics_prep.ui.application import build_app
    class Teacher:
        def ask(self,prompt,system=''):
            assert '合力' in prompt and 'recent_dialogue' in prompt
            assert 'correct_answer' not in prompt
            return {'text':'你认为加速度和合力方向有什么关系？', 'mode':'online','error':None}
    app=build_app(service,lambda:Teacher())
    fns={f.fn.__name__:f.fn for f in app.fns.values() if f.fn}
    values=fns['foundation']('newton')
    sid,qid=values[:2]
    text,*rest=fns['tutor_chat'](sid,qid,'我不会',False)
    assert '加速度' in text
    text,*rest=fns['tutor_chat'](sid,qid,'答案：3',False)
    assert '判分' in text and rest[1]['interactive']
    resumed=LearningService(service.path)
    assert resumed.tutor_history(sid)[-1]['kind']=='final'

def test_routes_choose_from_saved_weakness_and_due(service):
    sid=service.start_route('从零开始','quantum')
    q=service.next(sid)
    assert q['subject']=='quantum'
    service.submit(sid,q['id'],'0','route-wrong')
    weak=service.start_route('专项补弱','quantum')
    assert service.next(weak)['topic_ids']==q['topic_ids']
    with pytest.raises(ValueError,match='暂无到期'):
        service.start_route('到期复习','quantum')
    with pytest.raises(ValueError,match='请选择'):
        service.start_route('指定章节')

@pytest.mark.parametrize('model', ['newton','born'])
def test_generated_answers_grade(model):
    from physics_prep.diagnosis.math_grader import grade
    for i in range(10):
        q=generate(model,'t',i)
        assert grade(q['correct_answer'],q['correct_answer'],'numeric')['status']=='correct'
        assert q['machine_validated'] and not q['human_verified']
