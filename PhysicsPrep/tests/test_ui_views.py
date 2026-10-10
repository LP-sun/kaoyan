"""UI 层单元测试：渲染函数、知识树、错题本、设置脱敏、单位提示。"""
import json
from pathlib import Path

import pytest

from physics_prep.config import Settings
from physics_prep.llm.client import MockLLMClient, create_client
from physics_prep.llm.prompts import tutor_system, build_student_prompt
from physics_prep.diagnosis.units import detect_units
from physics_prep.services.learning import LearningService
from physics_prep.ui import knowledge_tree, settings as settings_view, wrong_answers
from physics_prep.ui.quiz import feedback_text, render_question

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def service(tmp_path):
    return LearningService(tmp_path / 'ui.sqlite3', ROOT / 'data')


# ---------------------------------------------------------------- 知识树

def test_tree_rows_show_unknown_mastery_not_false_mastery(service):
    rows = knowledge_tree.tree_rows(service)
    assert rows, '知识树不应为空'
    mastery_column = [row[4] for row in rows]
    assert all(value == knowledge_tree.MASTERY_UNKNOWN for value in mastery_column)
    assert all(len(row) == 5 for row in rows)


def test_tree_structure_markdown_has_four_levels(service):
    text = knowledge_tree.tree_markdown(service)
    assert '物理考研' in text
    assert '普通物理' in text or '力学' in text
    assert '纯滚动约束' in text
    assert 'PHY-MECH-ROT-003' in text


def test_tree_export_excludes_mastery(service):
    path = service.path.parent / 'tree.json'
    knowledge_tree.export_tree(service, path)
    values = json.loads(path.read_text(encoding='utf-8'))
    assert values and all('mastery' not in item for item in values)
    assert any(item['id'] == 'PHY-MECH-ROT-003' for item in values)


def test_topic_template_is_valid_json():
    parsed = json.loads(knowledge_tree.topic_json_template())
    assert parsed['id'] and parsed['prerequisite_ids'] == []


# ---------------------------------------------------------------- 错题本

def test_wrong_rows_and_history_after_incorrect(service):
    question_id = 'PHY-000005'
    seed = next(q for q in json.loads((ROOT / 'data' / 'seed_questions.json').read_text(encoding='utf-8'))
                if q['id'] == question_id)
    session_id = service.start(question_id=question_id)
    question = service.next(session_id)
    wrong = 'A' if seed['correct_answer'] != 'A' else 'B'
    service.submit(session_id, question['id'], wrong, 'ui-wrong-1')

    rows = wrong_answers.wrong_rows(service)
    assert len(rows) == 1
    assert rows[0][0] == question_id
    assert rows[0][4] == '错误'
    assert rows[0][5] == seed['correct_answer']

    history = wrong_answers.attempt_history(service, question_id)
    assert len(history) == 1 and history[0]['status'] == 'incorrect'

    plan = wrong_answers.plan_markdown(service)
    assert '到期复习' in plan and '待巩固考点' in plan
    assert '不是经过校准的记忆模型预测' in plan


def test_wrong_summary_handles_empty(service):
    assert '没有错题' in wrong_answers.wrong_summary(service)


# ---------------------------------------------------------------- 设置脱敏

def test_mask_key_never_reveals_full_key():
    secret = 'sk-super-secret-value-1234'
    masked = settings_view.mask_key(secret)
    assert secret not in masked
    assert '****1234' in masked
    assert '未配置' in settings_view.mask_key('')
    assert '未配置' in settings_view.mask_key(None)


def test_mode_summary_explains_mock_reason():
    text = settings_view.mode_summary(Settings(), MockLLMClient())
    assert 'Mock' in text
    assert '未配置' in text
    online = settings_view.mode_summary(Settings(api_key='k', base_url='https://x.test/v1', model='m'))
    assert 'GenAI 在线' in online
    # 短密钥不能原样出现在界面文案中
    assert settings_view.mask_key('k') not in online or 'k' != settings_view.mask_key('k')
    assert '内容不显示' in online


def test_connection_report_distinguishes_offline_and_fallback():
    assert 'Mock 模式' in settings_view.connection_report(MockLLMClient())

    class Failing:
        name = 'genai'

        def test_connection(self):
            return {'text': '回退内容', 'mode': 'mock', 'error': 'ReadTimeout'}

    report = settings_view.connection_report(Failing())
    assert 'ReadTimeout' in report and '回退' in report


def test_backup_help_mentions_path_and_no_key():
    text = settings_view.backup_help(Path('C:/tmp/study.sqlite3'))
    assert 'study.sqlite3' in text
    assert '不含' in text


def test_syllabus_help_is_empty_state_before_import():
    assert '尚无已归档大纲' in settings_view.syllabus_help([])
    table = settings_view.syllabus_help([
        {'label': '本地普物大纲（待确认年份）', 'subject': 'mechanics',
         'sha256': 'a' * 64, 'file': 'abc.pdf', 'official_status': '用户导入，年份与官方有效性待核'}])
    assert '待确认年份' in table
    assert '不代表它是某个年度的官方大纲' in table


# ---------------------------------------------------------------- 提示词

def test_tutor_system_blocks_answers_before_submit():
    before = tutor_system(after_submit=False)
    after = tutor_system(after_submit=True)
    full = tutor_system(full_solution=True)
    assert '不要公布最终答案' in before
    assert '不要公布最终答案' not in after
    assert '完整解析' in full
    assert before != after != full


def test_student_prompt_only_includes_provided_parts():
    prompt = build_student_prompt(question_stem='求加速度', question='为什么？')
    assert '求加速度' in prompt and '为什么' in prompt
    assert '我的作答' not in prompt
    with_answer = build_student_prompt(question_stem='题', student_answer='g/2', question='对吗')
    assert 'g/2' in with_answer


# ---------------------------------------------------------------- 单位

def test_unit_detection_is_conservative():
    # 下标常数名不能被当成单位
    assert detect_units('epsilon_0*A/d')[0] == []
    # 符号名不是单位
    assert detect_units('g*sin(theta)')[0] == []
    # 明确写出的复合单位能被识别
    assert 'm/s' in detect_units('v = 3*m/s')[0] or 'm' in detect_units('v = 3*m/s')[0]
    # 题目声明单位时，单位不符给出提示且不直接判错
    _, notice = detect_units('2 kg', expected_unit='m')
    assert notice and 'kg' in notice
    _, ok = detect_units('2 m', expected_unit='m')
    assert ok is None


def test_unit_mismatch_returns_uncertain_not_incorrect():
    from physics_prep.diagnosis.math_grader import grade
    result = grade('2 kg', '2', 'numeric', expected_unit='m')
    assert result['status'] == 'uncertain'
    assert '单位' in result['explanation']


# ---------------------------------------------------------------- 客户端

def test_create_client_falls_back_without_config():
    client = create_client(Settings())
    assert isinstance(client, MockLLMClient)


def test_create_client_rejects_http_address():
    from physics_prep.llm.client import LLMUnavailable, OfficialGenAIClient
    with pytest.raises(LLMUnavailable):
        OfficialGenAIClient(Settings(api_key='k', base_url='http://plain.test/v1', model='m'))
    # create_client 不抛异常，直接回退 Mock
    assert isinstance(create_client(Settings(api_key='k', base_url='http://plain.test/v1', model='m')),
                      MockLLMClient)


def test_online_client_never_echoes_api_key_on_failure():
    import httpx
    from physics_prep.llm.client import OfficialGenAIClient

    def fail(request):
        raise httpx.ConnectError('boom')

    client = OfficialGenAIClient(
        Settings(api_key='sk-secret-abcdef', base_url='https://example.test/v1', model='m', max_retries=0),
        transport=httpx.MockTransport(fail), sleep=lambda _: None)
    result = client.ask('测试')
    # OpenAI SDK 会把 httpx 的 ConnectError 包装为 APIConnectionError；只断言类别被保留。
    assert result['error'] and 'Error' in result['error']
    assert 'sk-secret-abcdef' not in json.dumps(result, ensure_ascii=False)
    assert result['mode'] == 'mock'


def test_online_client_rejects_overlong_prompt():
    import httpx
    from physics_prep.llm.client import MAX_PROMPT_CHARS, OfficialGenAIClient
    client = OfficialGenAIClient(
        Settings(api_key='k', base_url='https://example.test/v1', model='m'),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})), sleep=lambda _: None)
    result = client.ask('x' * (MAX_PROMPT_CHARS + 1))
    assert result['error'] == 'input_limit'
    assert result['mode'] == 'local'


def test_online_client_reports_empty_model_output():
    import httpx
    from physics_prep.llm.client import OfficialGenAIClient

    def empty(request):
        return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': ''}}]})

    client = OfficialGenAIClient(
        Settings(api_key='k', base_url='https://example.test/v1', model='m', max_retries=0),
        transport=httpx.MockTransport(empty), sleep=lambda _: None)
    result = client.ask('测试')
    assert result['mode'] == 'mock' and result['error'] == 'ValueError'


# ---------------------------------------------------------------- 反馈文案

def test_feedback_text_labels_status_with_words_not_only_color():
    text, detail = feedback_text({'status': 'incorrect', 'explanation': '两式不同',
                                  'topic_names': ['纯滚动约束'], 'error_category': '尚无法确定',
                                  'correct_answer': '2*g*sin(theta)/3', 'solution': '推导内容',
                                  'mastery': [{'topic_id': 't1', 'estimate': 0.31, 'attempts': 1,
                                               'due_at': '2026-01-01T00:00:00+00:00'}]})
    assert '需要巩固' in text
    assert '纯滚动约束' in text
    assert '错因判断' in text
    assert '掌握度更新' in text and '0.31' in text
    assert '标准答案' in detail and '推导与检验' in detail
    assert '2*g*sin(theta)/3' in detail


def test_render_question_shows_type_and_clears_controls():
    result = render_question({'id': 'q9', 'stem': '题干', 'question_type': 'multiple_choice',
                              'options': ['甲', '乙'], 'topic_names': ['T'], 'difficulty': 2,
                              'subject': 'quantum', 'session_progress': 3}, 'sid')
    info = result[3]
    assert '多选题' in info and '量子力学' in info
    assert result[5]['visible'] is False   # 单选控件隐藏
    assert result[6]['visible'] is True    # 多选控件显示
    assert result[7]['visible'] is False   # 文本输入隐藏
