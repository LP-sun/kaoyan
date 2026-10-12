import json
import pytest
from physics_prep.questions.importer import adapt_writing_record
from physics_prep.services.learning import LearningService

def fixture_record():
    # Synthetic schema fixture, not an assertion that a textbook was reviewed.
    return {'id':'BK-fixture','subject':'mechanics','difficulty':1,'difficulty_source':'fixture_design',
        'statement':'schema fixture','question_type':'numeric','syllabus_topics':['fixture-topic'],
        'review':{'statement_status':'verified','solution_status':'checked','reviewer_kind':'human',
            'statement_evidence':'synthetic fixture','solution_evidence':'synthetic fixture'},
        'solution':{'steps':['fixture step'],'final_answer':'1','checks':['fixture check']}}

def test_status_strings_alone_do_not_admit_writing():
    r=fixture_record(); r['review'].pop('reviewer_kind')
    with pytest.raises(ValueError,match='人工'):
        adapt_writing_record(r)

def test_missing_difficulty_is_not_guessed():
    r=fixture_record(); r.pop('difficulty')
    with pytest.raises(ValueError,match='猜测'):
        adapt_writing_record(r)

def test_empty_solution_cannot_enter_pool():
    r=fixture_record(); r['solution']['final_answer']=''
    with pytest.raises(ValueError,match='非空'):
        adapt_writing_record(r)

def test_zero_is_a_valid_nonempty_answer():
    r=fixture_record(); r['solution']['final_answer']=0
    assert adapt_writing_record(r)['correct_answer']==0

def test_writing_json_uses_real_import_chain(tmp_path):
    s=LearningService(tmp_path/'adapter.sqlite3')
    s.save_topic({'id':'fixture-topic','name':'synthetic fixture topic'})
    r=fixture_record(); file=tmp_path/'writing.json'; file.write_text(json.dumps(r),encoding='utf-8')
    assert s.import_questions(file)==1
    q=s.list_questions()[0]
    assert q['id']==r['id'] and q['writing_record']==r and q['human_verified']
