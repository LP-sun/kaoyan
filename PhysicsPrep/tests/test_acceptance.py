"""端到端验收场景（场景 A / B / C）与 Mock 模式全流程。

这些测试只使用公开服务接口与固定题库，不需要网络：
- 场景 A：力学诊断 → 作答 → 解析 → 下一题 → 诊断报告；
- 场景 B：纯滚动题答错 → 记录错误 → 降难度或转前置考点 → 提供讲解 → 安排复习；
- 场景 C：完成一轮练习 → 关闭服务 → 重新打开 → 历史、掌握度、错题仍在。
"""
import json
from pathlib import Path

import pytest

from physics_prep.config import Settings
from physics_prep.diagnosis.math_grader import grade
from physics_prep.llm.client import MockLLMClient, create_client
from physics_prep.services.learning import LearningService

ROOT = Path(__file__).resolve().parents[1]
SEEDS = json.loads((ROOT / 'data' / 'seed_questions.json').read_text(encoding='utf-8'))
SEED_BY_ID = {q['id']: q for q in SEEDS}


@pytest.fixture
def service(tmp_path):
    return LearningService(tmp_path / 'study.sqlite3', ROOT / 'data')


def answer_correctly(question):
    """公开题不含答案，正确答案从种子题库按 ID 取（模拟学生自己算对）。"""
    return SEED_BY_ID[question['id']]['correct_answer']


def answer_wrongly(question):
    """给出一个“能通过解析但确实错误”的作答，保证判分为 incorrect 而不是 uncertain。"""
    seed = SEED_BY_ID[question['id']]
    kind = seed['question_type']
    correct = seed['correct_answer']
    if kind == 'single_choice':
        for option in ('A', 'B', 'C', 'D'):
            if option != correct:
                return option
        return 'D'
    if kind == 'multiple_choice':
        options = list(seed.get('options') or [])
        for index in range(len(options)):
            letter = chr(65 + index)
            if letter not in set(correct):
                return [letter]
        return ['Z']
    # 符号题/数值题：提交一个可解析但不等价的表达式。
    return '1' if str(correct).strip() != '1' else '2'


def submit_current(service, session_id, question, token):
    return service.submit(session_id, question['id'], answer_wrongly(question), token)


# ------------------------------------------------------------------ 场景 A

def test_scenario_a_normal_diagnosis(service):
    """场景 A：正常诊断 —— 开始 → 答题 → 看解析 → 下一题 → 报告。"""
    session_id = service.start('mechanics')
    assert session_id

    first = service.next(session_id)
    assert first and first['question_type']
    # 作答前不能拿到答案或解析
    assert 'correct_answer' not in first and 'solution' not in first

    feedback = service.submit(session_id, first['id'], answer_correctly(first), 'a-token-1')
    assert feedback['status'] == 'correct'
    assert feedback['correct_answer'] == SEED_BY_ID[first['id']]['correct_answer']
    assert feedback['solution']
    assert feedback['topic_names']
    assert feedback['mastery'] and feedback['mastery'][0]['due_at']

    second = service.next(session_id)
    assert second and second['id'] != first['id']

    frame = service.report(session_id)
    assert frame['attempts'] == 1
    assert frame['accuracy'] == 1.0
    assert frame['topics']


def test_scenario_a_covers_multiple_question_types(service):
    """场景 A 扩展：四类可判分题型都能完成一次“作答 → 判分”闭环。"""
    seen = set()
    for question in SEEDS:
        if question['question_type'] == 'short_answer':
            continue
        result = grade(question['correct_answer'], question['correct_answer'],
                       question['question_type'], question)
        assert result['status'] == 'correct', (question['id'], result)
        seen.add(question['question_type'])
    assert {'single_choice', 'multiple_choice', 'numeric', 'symbolic'} <= seen


# ------------------------------------------------------------------ 场景 B

def test_scenario_b_error_remedy(service):
    """场景 B：答错纯滚动题 → 记录错误 → 补救选题 → 讲解 → 安排复习。"""
    rolling_id = 'PHY-000006'  # 纯滚动约束
    topic_ids = SEED_BY_ID[rolling_id]['topic_ids']
    assert topic_ids, '纯滚动题必须关联知识点'

    session_id = service.start(question_id=rolling_id)
    question = service.next(session_id)
    assert question and question['id'] == rolling_id

    feedback = submit_current(service, session_id, question, 'b-token-1')
    assert feedback['status'] == 'incorrect'
    assert feedback['correct_answer']
    assert feedback['solution']

    # 错题被记录，且带完整快照便于日后回看
    wrong = service.wrong_answers()
    assert len(wrong) == 1
    assert wrong[0]['question_id'] == rolling_id
    assert wrong[0]['snapshot']['id'] == rolling_id

    # 掌握度与复习计划都被更新，且掌握度不是“已掌握”
    mastery = {m['topic_id']: m for m in service.dashboard()['mastery']}
    assert topic_ids[0] in mastery
    assert mastery[topic_ids[0]]['estimate'] < 0.5
    assert mastery[topic_ids[0]]['attempts'] == 1
    with service.factory() as session:
        from sqlalchemy import select
        from physics_prep.database.models import ReviewSchedule
        schedules = list(session.scalars(select(ReviewSchedule)))
    assert schedules and schedules[0].interval_days == 1

    # 补救：答错后不会立刻重复同一题，且优先转向前置或低难度考点
    following = service.next(session_id)
    assert following is None or following['id'] != rolling_id


def test_scenario_b_selector_prefers_remedy_and_avoids_loop(service):
    """场景 B 的选题部分：补救优先、避免在同一薄弱考点无限循环。"""
    from physics_prep.diagnosis.selector import select_question

    questions = [
        {'id': 'roll', 'topic_ids': ['roll'], 'difficulty': 3, 'verified': True, 'source_type': 'original'},
        {'id': 'pre', 'topic_ids': ['kin'], 'difficulty': 1, 'verified': True, 'source_type': 'original'},
        {'id': 'roll2', 'topic_ids': ['roll'], 'difficulty': 1, 'verified': True, 'source_type': 'original'},
    ]
    history = [{'question_id': 'roll', 'status': 'incorrect', 'topic_ids': ['roll']}]
    chosen = select_question(questions, history, {'roll': {'estimate': .2}}, {'roll': ['kin']})
    assert chosen['id'] == 'pre'
    assert '补救' in chosen['recommendation_reason'] or '前置' in chosen['recommendation_reason']

    # 连续同一考点后不再继续加码该考点
    history = history * 4
    chosen = select_question(questions, history, {'roll': {'estimate': .1}, 'kin': {'estimate': .1}}, {'roll': []})
    assert chosen['id'] != 'roll2'


# ------------------------------------------------------------------ 场景 C

def test_scenario_c_restart_recovery(tmp_path):
    """场景 C：重启恢复 —— 新实例读回历史、掌握度与错题。"""
    db_path = tmp_path / 'restart.sqlite3'
    first = LearningService(db_path, ROOT / 'data')

    session_id = first.start('mechanics')
    correct = None
    wrong = None
    for index in range(4):
        question = first.next(session_id)
        if not question:
            break
        if index == 0:
            correct = question
            first.submit(session_id, question['id'], answer_correctly(question), f'c-ok-{index}')
        else:
            wrong = question
            first.submit(session_id, question['id'], answer_wrongly(question), f'c-bad-{index}')

    before_dashboard = first.dashboard()
    before_tree = {t['id']: t['mastery'] for t in first.topic_tree()}
    before_wrong = first.wrong_answers()
    assert before_wrong, '需要至少一条错题才能验证恢复'
    assert any(v is not None for v in before_tree.values())

    # 模拟“关闭程序”：释放连接后重新打开同一个数据库文件
    first.engine.dispose()
    second = LearningService(db_path, ROOT / 'data')

    assert second.resume() == session_id
    after_wrong = second.wrong_answers()
    assert [w['question_id'] for w in after_wrong] == [w['question_id'] for w in before_wrong]
    assert second.report(session_id)['attempts'] == before_dashboard['today_count']
    after_tree = {t['id']: t['mastery'] for t in second.topic_tree()}
    assert after_tree == before_tree
    # 重启后不会重复导入题库
    assert len(second.list_questions()) == len(first.list_questions())
    assert len(second.topic_tree()) == len(first.topic_tree())


def test_scenario_c_restart_continues_same_question(tmp_path):
    """重启后继续上次学习，会回到未提交的那道题而不是换题。"""
    db_path = tmp_path / 'resume.sqlite3'
    first = LearningService(db_path, ROOT / 'data')
    session_id = first.start('quantum')
    pending = first.next(session_id)
    first.engine.dispose()

    second = LearningService(db_path, ROOT / 'data')
    assert second.resume() == session_id
    resumed = second.next(second.resume())
    assert resumed['id'] == pending['id']


# ------------------------------------------------------------- Mock 模式

def test_mock_mode_full_flow_without_api_key(tmp_path):
    """完全没有 API Key 时，判分、记录、诊断、AI 引导全部可用。"""
    settings = Settings()  # 全部为空
    assert settings.effective_mock
    client = create_client(settings)
    assert isinstance(client, MockLLMClient)
    assert client.test_connection()['mode'] == 'mock'

    service = LearningService(tmp_path / 'mock.sqlite3', ROOT / 'data')
    session_id = service.start()
    question = service.next(session_id)
    feedback = service.submit(session_id, question['id'], answer_correctly(question), 'mock-1')
    assert feedback['status'] == 'correct'

    hint = service.hint(question['id'])
    assert hint
    suggestion = client.ask('这道题该用什么定律？')
    assert suggestion['mode'] == 'mock' and suggestion['error'] is None
    assert 'Mock' in suggestion['text']


def test_mock_client_never_claims_to_be_model_reasoning():
    client = MockLLMClient()
    for system in ('', '作答前提示', '已提交'):
        result = client.ask('解释一下', system=system)
        assert result['mode'] == 'mock'
        assert '非模型推理' in result['text']
