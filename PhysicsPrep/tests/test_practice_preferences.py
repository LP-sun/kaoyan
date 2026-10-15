from copy import deepcopy
from pathlib import Path
import pytest
from sqlalchemy import select, func
from physics_prep.services.learning import LearningService
from physics_prep.services.practice import PracticeSessionController
from physics_prep.database.models import Attempt, MasteryRecord, ReviewSchedule
from physics_prep.questions.generation import generate, SUPPORTED_MODELS, MODEL_PERIODS
from physics_prep.questions.generated_validation import validate_generated
from physics_prep.questions.candidates import MODEL_TOPICS
from physics_prep.diagnosis.selector import select_question


@pytest.fixture
def service(tmp_path):
    return LearningService(tmp_path/'preferences.sqlite3',Path(__file__).parents[1]/'data')


def evidence(service):
    with service.factory() as s:
        return tuple(s.scalar(select(func.count()).select_from(model)) for model in (Attempt,MasteryRecord,ReviewSchedule))


def test_easy_skip_is_atomic_ungraded_persistent_and_rejects_stale(service):
    c=PracticeSessionController(service)
    v=c.start('general'); sid=v['session_id']; q=v['question']
    before=evidence(service)
    after=c.too_easy(sid,q['id'])
    assert after['question']['id']!=q['id'] and evidence(service)==before
    assert after['summary']['attempts']==0 and after['summary']['too_easy_count']==1
    topic=q['topic_ids'][0]
    assert after['state']['difficulty_preferences'][topic]==min(5,q['difficulty']+1)
    with pytest.raises(ValueError): c.too_easy(sid,q['id'])
    assert c.view(sid)['summary']['too_easy_count']==1
    restarted=PracticeSessionController(LearningService(service.path))
    assert restarted.resume()['state']['difficulty_preferences']==after['state']['difficulty_preferences']
    restarted.finish(sid)
    assert restarted.start()['state']['difficulty_preferences'][topic]==min(5,q['difficulty']+1)


def test_preference_raises_level_without_mastery_or_ignoring_prerequisites():
    def q(key,level,topic='t'):
        return dict(id=key,topic_ids=[topic],difficulty=level,verified=True,source_type='original',question_type='single_choice')
    pool=[q('easy',1),q('hard',3)]
    assert select_question(pool,[],{})['id']=='easy'
    result=select_question(pool,[],{},difficulty_preferences={'t':3})
    assert result['id']=='hard' and '过于简单' in result['recommendation_reason']
    assert select_question([q('pre',1,'p'),q('combined',5)],[],{}, {'t':['p']},difficulty_preferences={'t':5})['id']=='pre'


@pytest.mark.parametrize('model',SUPPORTED_MODELS)
def test_choice_options_unique_and_tampering_rejected(model):
    for variant in range(MODEL_PERIODS[model]):
        q=generate(model,MODEL_TOPICS[model],variant,'single_choice')
        assert q['machine_validated'] and not q['human_verified']
        assert len(q['options'])==4
        assert q['id']!=generate(model,MODEL_TOPICS[model],variant)['id']
    altered=deepcopy(q); altered['options'][0]=altered['options'][1]
    assert not validate_generated(altered)['passed']
    altered=deepcopy(q); altered['correct_answer']=chr(65+(ord(q['correct_answer'])-64)%4)
    assert not validate_generated(altered)['passed']


def test_choice_filter_survives_generation_remediation_restart_and_live_switch(service):
    c=PracticeSessionController(service)
    v=c.start('quantum',question_filter='choice'); sid=v['session_id']
    generated=False
    for i in range(18):
        q=v['question']
        assert q['question_type'] in ('single_choice','multiple_choice')
        generated|=q['id'].startswith('GEN-')
        saved=next(x for x in service.list_questions() if x['id']==q['id'])
        c.submit(sid,q['id'],'Z' if i==3 else saved['correct_answer'],f'choice-{i}')
        v=c.next(sid)
    assert generated
    assert PracticeSessionController(LearningService(service.path)).resume()['state']['question_filter']=='choice'
    other=c.start('general','chapter','PHY-MECH-DYN-001')
    before=evidence(service)
    filtered=c.set_question_filter(other['session_id'],'choice')
    assert filtered['question']['question_type'] in ('single_choice','multiple_choice')
    assert evidence(service)==before
    c.set_question_filter(other['session_id'],'all')
    with pytest.raises(ValueError): c.set_question_filter(other['session_id'],'invalid')


def test_easy_during_remediation_retains_pending_target(service):
    c=PracticeSessionController(service)
    v=c.start('general','chapter','PHY-MECH-ROT-003'); sid=v['session_id']
    q=v['question']; c.submit(sid,q['id'],'0','wrong')
    v=c.next(sid); before=evidence(service)
    v=c.too_easy(sid,v['question']['id'])
    assert q['topic_ids'][0] in v['summary']['needs_independent_retest']
    assert evidence(service)==before and not v['remedy']


def test_choice_filter_does_not_restore_edited_cache_as_numeric(service):
    c=PracticeSessionController(service)
    topic=MODEL_TOPICS['newton']
    cached=service.store_generated(generate('newton',topic,0,'single_choice'))
    changed=deepcopy(cached)
    changed.update(question_type='numeric',correct_answer='3',verified=True,options=[],source_type='original')
    service.save_question(changed)
    view=c.start('general','chapter',topic,'choice')
    q=view['question']
    assert q['question_type'] in ('single_choice','multiple_choice')
    state=c._load(view['session_id'])
    generated=c._generate(state,topic,set())
    assert generated['id']!=cached['id'] and generated['question_type']=='single_choice'
