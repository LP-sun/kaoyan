"""自适应诊断的题型过滤：只主动派发可确定性判分的题型。

背景（来自真实使用记录）：开放题（short_answer）在诊断流里只能得到 uncertain，
既不更新掌握度又占用一次诊断名额。开放题仍可通过“精确重做题目 ID”主动练习；
候选池只剩开放题时选择器退回照常派发，而不是让会话无题可做。
"""
import pytest

from physics_prep.diagnosis.selector import AUTO_GRADED_TYPES, select_question
from physics_prep.services.learning import LearningService
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def service(tmp_path):
    return LearningService(tmp_path / 'study.sqlite3', ROOT / 'data')


def make(qid, qtype, topics, difficulty=2):
    return {'id': qid, 'question_type': qtype, 'topic_ids': topics, 'difficulty': difficulty,
            'verified': True, 'source_type': 'original'}


def test_open_ended_loses_to_gradable_even_with_stronger_signals():
    """开放题即使处在“到期复习”考点上信号更强，自适应诊断仍选客观题。"""
    questions = [make('obj', 'numeric', ['kin']), make('open', 'short_answer', ['rot'])]
    chosen = select_question(questions, [], {}, None, {'rot'})
    assert chosen['id'] == 'obj'


def test_open_ended_still_served_when_pool_has_nothing_else():
    questions = [make('open', 'short_answer', ['rot'])]
    chosen = select_question(questions, [], {}, None, set())
    assert chosen and chosen['id'] == 'open'


def test_legacy_fixtures_without_question_type_unaffected():
    """旧测试夹具没有 question_type 字段：过滤后为空时必须保持原候选池。"""
    questions = [{'id': 'a', 'topic_ids': ['t'], 'difficulty': 1, 'verified': True,
                  'source_type': 'original'}]
    assert select_question(questions, [], {}, None, set())['id'] == 'a'


def test_gradable_type_set_matches_deterministic_grader():
    assert AUTO_GRADED_TYPES == {'single_choice', 'multiple_choice', 'numeric', 'symbolic',
                                 'numeric_calculation', 'symbolic_expression'}
    assert 'short_answer' not in AUTO_GRADED_TYPES


def test_seed_bank_adaptive_pick_is_never_short_answer(service):
    questions = service.list_questions()
    due = {t for q in questions for t in q['topic_ids']}
    chosen = select_question(questions, [], {}, None, due)
    assert chosen and chosen['question_type'] != 'short_answer'


def test_diagnosis_session_serves_only_gradable_until_exhausted(service):
    """跑满一轮自适应诊断：派发的题目全部可确定性判分，开放题不占名额。"""
    sid = service.start()
    served = []
    while len(served) < 40:
        question = service.next(sid)
        if question is None or question['id'] in served:
            break
        assert question['question_type'] != 'short_answer'
        served.append(question['id'])
        service.submit(sid, question['id'], 'placeholder-wrong', f'tok-{len(served)}')
    assert len(served) == 29  # 题库 30 题中 29 题可自动判分，全部派发过


def test_symbol_error_message_lists_allowed_symbols():
    """判分反馈要告诉用户本题可用哪些符号，而不是只说“未允许”。"""
    from physics_prep.diagnosis.math_grader import grade
    result = grade('sqrt(2*g*h)', 'g*sin(theta)', 'symbolic',
                   options={'allowed_symbols': ['g', 'theta']})
    assert result['status'] == 'uncertain'
    assert '本题可用符号：g、theta' in result['explanation']
