"""在线（GenAI）模式的界面级端到端接线测试。

目的：在没有学校真实凭据的情况下，仍然验证“配置了合法 GenAI”时的完整链路——
`Settings` → `create_client` → `OfficialGenAIClient` → UI 事件处理器 → 界面文案。

做法：用 `httpx.MockTransport` 提供确定性的 Chat Completions 响应，
并把 `httpx.Client` 临时替换为注入了该 transport 的构造器，
这样 `create_client` 走的是**真实**的 `OfficialGenAIClient.ask()` 代码路径，
唯一被替换的是网络传输层。

同时直接调用 Gradio 注册的处理器（从 `app.fns` 取），确保界面接线本身是通的。
"""
import json
from pathlib import Path

import httpx
import pytest

from physics_prep.config import Settings
from physics_prep.llm import client as client_module
from physics_prep.llm.client import OfficialGenAIClient, create_client
from physics_prep.services.learning import LearningService
from physics_prep.ui.application import build_app
from physics_prep.ui.settings import connection_report, mask_key, mode_summary

ROOT = Path(__file__).resolve().parents[1]
FAKE_KEY = 'sk-test-only-placeholder-key-0001'
FAKE_URL = 'https://genai.example.edu/v1'
FAKE_MODEL = 'test-chat-model'

ONLINE_SETTINGS = Settings(api_key=FAKE_KEY, base_url=FAKE_URL, model=FAKE_MODEL, max_retries=2)


def completion(text='连接成功'):
    return {'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': FAKE_MODEL,
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text},
                         'finish_reason': 'stop'}]}


def patch_transport(monkeypatch, handler):
    """让所有 httpx 客户端把请求交给 `handler` 处理（仅本次测试）。

    **不能**替换 `httpx.Client` 本身：OpenAI SDK 在 import 时就定义了
    `class _DefaultHttpxClient(httpx.Client)`，替换基类会让 SDK 直接 import 失败
    （TypeError: function() argument 'code' must be code, not str）。
    因此改为替换基类传输层的 `handle_request`，这是所有 httpx 客户端实际发请求的入口。
    OpenAI SDK 的 `_DefaultHttpxClient` 没有覆写它，所以补丁会生效。
    """
    def handle_request(self, request):  # noqa: ANN001 - 需要与 httpx 签名一致
        return httpx.MockTransport(handler).handle_request(request)

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', handle_request)


@pytest.fixture
def service(tmp_path):
    svc = LearningService(tmp_path / 'online.sqlite3', ROOT / 'data')
    yield svc
    svc.engine.dispose()


def handlers(app):
    """按名字取出 Gradio 注册的处理器。

    `build_app` 里的 `safe()` 保留原函数名（或用显式名字注册），
    因此可以按语义名字定位处理器，直接验证界面接线。
    """
    result = {}
    for wrapper in app.fns.values():
        fn = getattr(wrapper, 'fn', None)
        if fn is not None and getattr(fn, '__name__', None):
            result.setdefault(fn.__name__, fn)
    return result


def test_handlers_are_addressable_by_name(service):
    """防止处理器再次退化成 wrapped_23 这类无法定位的名字。"""
    app = build_app(service, lambda: create_client(ONLINE_SETTINGS), ONLINE_SETTINGS)
    names = set(handlers(app))
    for expected in ('start', 'resume', 'advance', 'submit', 'ask', 'connection',
                     'configure', 'backup', 'restore', 'tree_view', 'refresh_dashboard'):
        assert expected in names, f'缺少具名处理器: {expected}'


# ------------------------------------------------------- 客户端层：在线成功

def test_valid_settings_create_online_client_and_connect(monkeypatch):
    seen = []

    def respond(request):
        seen.append(json.loads(request.content.decode('utf-8')))
        return httpx.Response(200, json=completion())

    patch_transport(monkeypatch, respond)
    client = create_client(ONLINE_SETTINGS)
    assert isinstance(client, OfficialGenAIClient)
    assert client.name == 'genai'

    result = client.test_connection()
    assert result['mode'] == 'online' and result['error'] is None
    assert '连接成功' in result['text']

    # 请求确实发到了配置的 path，且用的是标准 Chat Completions 结构
    assert seen and seen[0]['model'] == FAKE_MODEL
    assert [m['role'] for m in seen[0]['messages']] == ['system', 'user']


def test_online_failure_falls_back_to_mock_and_reports_category(monkeypatch):
    calls = []

    def fail(request):
        calls.append(1)
        raise httpx.ConnectError('network down')

    patch_transport(monkeypatch, fail)
    client = create_client(Settings(api_key=FAKE_KEY, base_url=FAKE_URL, model=FAKE_MODEL, max_retries=2))
    result = client.ask('解释牛顿第二定律')

    assert result['mode'] == 'mock'          # 已回退
    assert result['error'] and 'Error' in result['error']
    assert len(calls) == 3                   # 1 次 + 2 次重试
    assert FAKE_KEY not in json.dumps(result, ensure_ascii=False)


def test_online_client_retries_then_succeeds(monkeypatch):
    attempts = []

    def flaky(request):
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ReadTimeout('slow')
        return httpx.Response(200, json=completion('终于成功'))

    patch_transport(monkeypatch, flaky)
    client = create_client(Settings(api_key=FAKE_KEY, base_url=FAKE_URL, model=FAKE_MODEL, max_retries=2))
    result = client.ask('再试一次')

    assert result['mode'] == 'online' and '终于成功' in result['text']
    assert len(attempts) == 3


# --------------------------------------------- 界面层：在线模式的完整接线

def test_ui_settings_tab_reports_online_success(monkeypatch, service):
    def respond(request):
        return httpx.Response(200, json=completion())

    patch_transport(monkeypatch, respond)
    app = build_app(service, lambda: create_client(ONLINE_SETTINGS), ONLINE_SETTINGS)
    fns = handlers(app)

    report = fns['connection']()
    assert '连接成功（在线模型）' in report
    assert FAKE_KEY not in report          # 密钥不回显

    summary = mode_summary(ONLINE_SETTINGS)
    assert 'GenAI 在线' in summary
    assert FAKE_KEY not in summary


def test_ui_settings_tab_reports_fallback(monkeypatch, service):
    def fail(request):
        raise httpx.ConnectError('offline')

    patch_transport(monkeypatch, fail)
    app = build_app(service, lambda: create_client(ONLINE_SETTINGS), ONLINE_SETTINGS)
    fns = handlers(app)

    report = fns['connection']()
    assert '已回退 Mock' in report
    assert 'Error' in report
    assert FAKE_KEY not in report


def test_ui_ai_teacher_uses_online_model_before_and_after_submit(monkeypatch, service):
    prompts = []

    def respond(request):
        body = json.loads(request.content.decode('utf-8'))
        prompts.append(body['messages'])
        return httpx.Response(200, json=completion('先判断适用条件，再列方程。'))

    patch_transport(monkeypatch, respond)
    app = build_app(service, lambda: create_client(ONLINE_SETTINGS), ONLINE_SETTINGS)
    fns = handlers(app)

    # ---- 作答前：system 提示必须禁止公布答案
    before = fns['ask']('q-1', '', '这题该用什么定律？', False)
    assert '先判断适用条件' in before
    system_before = prompts[-1][0]['content']
    assert '不要公布最终答案' in system_before

    # ---- 提交后：允许给出完整解析
    session_id = service.start('mechanics')
    question = service.next(session_id)
    seed = next(q for q in json.loads((ROOT / 'data' / 'seed_questions.json').read_text(encoding='utf-8'))
                if q['id'] == question['id'])
    feedback = service.submit(session_id, question['id'], seed['correct_answer'], 'online-1')
    from physics_prep.ui.quiz import feedback_text
    summary, detail = feedback_text(feedback)

    after = fns['ask'](question['id'], summary, '为什么这里能用这个定律？', False)
    assert '先判断适用条件' in after
    system_after = prompts[-1][0]['content']
    assert '不要公布最终答案' not in system_after

    # ---- 用户主动索取完整解析
    fns['ask'](question['id'], summary, '请给我完整解析', True)
    assert '完整解析' in prompts[-1][0]['content']


def test_ui_configure_applies_valid_genai_parameters(monkeypatch, service):
    def respond(request):
        return httpx.Response(200, json=completion())

    patch_transport(monkeypatch, respond)
    settings = Settings(api_key=FAKE_KEY, base_url=FAKE_URL, model=FAKE_MODEL, max_retries=2)
    app = build_app(service, lambda: create_client(settings), settings)
    fns = handlers(app)

    # configure() 只更新运行期配置单元，不修改调用方传入的 Settings 对象
    # （这本身是好事：避免界面操作产生意外的全局副作用）。
    status = fns['configure'](FAKE_URL, FAKE_MODEL, 45, 3, False)
    assert 'GenAI 在线' in status
    assert FAKE_KEY not in status
    assert FAKE_URL in status and FAKE_MODEL in status
    # 注意：with_parameters 会把超时转成 float，界面显示为 "45.0 秒"。
    assert '超时：45.0 秒' in status and '最大重试：3' in status
    assert settings.timeout == 60 and settings.max_retries == 2   # 原对象未被改动


def test_ui_configure_switching_to_mock_stops_network(monkeypatch, service):
    calls = []

    def respond(request):
        calls.append(1)
        return httpx.Response(200, json=completion())

    patch_transport(monkeypatch, respond)
    settings = Settings(api_key=FAKE_KEY, base_url=FAKE_URL, model=FAKE_MODEL, max_retries=2)
    app = build_app(service, lambda: create_client(settings), settings)
    fns = handlers(app)

    # 先确认在线模式下确实会发请求
    assert '连接成功（在线模型）' in fns['connection']()
    assert calls

    calls.clear()
    status = fns['configure'](FAKE_URL, FAKE_MODEL, 60, 2, True)   # 勾选 Mock
    assert 'Mock' in status
    assert '超时：60.0 秒' in status and '最大重试：2' in status
    # 切到 Mock 后连接测试不应再产生任何网络请求
    report = fns['connection']()
    assert 'Mock 模式' in report
    assert not calls


# ------------------------------------------------------- 界面文案完整性

def test_mode_summary_and_mask_for_online_config():
    summary = mode_summary(ONLINE_SETTINGS, None)
    assert 'GenAI 在线' in summary
    assert FAKE_KEY not in summary
    assert mask_key(FAKE_KEY) == f'已配置（长度 {len(FAKE_KEY)}，末四位 ****{FAKE_KEY[-4:]}）'


def test_connection_report_handles_missing_client():
    assert '尚未就绪' in connection_report(None)


def test_failure_never_labels_substitute_text_as_model_output(monkeypatch):
    """在线失败时返回的是替换内容，界面不得把它当成“模型的回答”。"""
    def fail(request):
        raise httpx.ConnectError('offline')

    patch_transport(monkeypatch, fail)
    client = create_client(Settings(api_key=FAKE_KEY, base_url=FAKE_URL, model=FAKE_MODEL, max_retries=0))
    result = client.ask('解释牛顿第二定律')
    assert result['mode'] == 'mock'
    assert result['fallback_text'] is True
    # OpenAI SDK 会把 httpx.ConnectError 包成自己的 APIConnectionError；
    # 这里只要求保留“某个连接类异常类别名”，不绑定具体类名。
    assert 'Connection' in result['error'] or 'Connect' in result['error']

    report = connection_report(client)
    assert '已回退 Mock' in report
    assert result['error'] in report
    assert '连接成功' not in report


def test_online_success_marks_text_as_model_output(monkeypatch):
    def respond(request):
        return httpx.Response(200, json=completion('这是模型的真实回答'))

    patch_transport(monkeypatch, respond)
    client = create_client(ONLINE_SETTINGS)
    result = client.ask('解释牛顿第二定律')
    assert result['mode'] == 'online'
    assert result['fallback_text'] is False
    assert result['error'] is None

    report = connection_report(client)
    assert '连接成功（在线模型）' in report
    assert '已回退 Mock' not in report
    assert '这是模型的真实回答' in report


def test_mock_client_marks_text_as_fallback():
    from physics_prep.llm.client import MockLLMClient
    result = MockLLMClient().ask('任意问题')
    assert result['mode'] == 'mock' and result['fallback_text'] is True
    assert '已回退' not in connection_report(MockLLMClient())   # 纯 Mock 不是“回退”
    assert 'Mock 模式' in connection_report(MockLLMClient())


def test_online_settings_effective_mock_is_false():
    assert ONLINE_SETTINGS.effective_mock is False
    assert Settings(api_key=FAKE_KEY, base_url=FAKE_URL).effective_mock is True   # 缺模型 ID
    assert Settings(api_key=FAKE_KEY, model=FAKE_MODEL).effective_mock is True    # 缺地址
    assert Settings(base_url=FAKE_URL, model=FAKE_MODEL).effective_mock is True   # 缺密钥
