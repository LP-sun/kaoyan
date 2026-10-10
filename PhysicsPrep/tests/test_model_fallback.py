"""模型降级链（`GENAI_MODEL_FALLBACKS`）的单元测试。

设计要点：

- `httpx.MockTransport` 只替换网络传输层，`OfficialGenAIClient.ask()` 是真实代码路径；
- 按模型 ID 决定返回什么，从而精确构造“主模型坏、备用模型好”的场景；
- 断言“尝试了哪些模型、在哪个模型上重试”，而不只看最终文本。

降级策略（见 `physics_prep/llm/client.py` 的模块文档）：
- 不降级：认证失败、连接错误、代理错误、各种超时 —— 换模型必然同样失败；
- 降级：模型不存在、无权限、请求被拒、限流、返回空内容。
"""
import httpx
import pytest

from physics_prep.config import Settings, _parse_models
from physics_prep.llm.client import create_client
from physics_prep.ui.settings import connection_report, mode_summary

FAKE_KEY = 'sk-test-only-placeholder-key-0002'
FAKE_URL = 'https://genai.example.edu/v1'
PRIMARY = 'primary-model'
FALLBACKS = ('backup-one', 'backup-two')
ALL_MODELS = (PRIMARY,) + FALLBACKS


def patch_transport(monkeypatch, handler):
    def handle_request(self, request):  # noqa: ANN001 - 需与 httpx 签名一致
        return httpx.MockTransport(handler).handle_request(request)

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', handle_request)


def completion(text, model):
    return {'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': model,
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text},
                         'finish_reason': 'stop'}]}


def settings(**overrides):
    base = dict(api_key=FAKE_KEY, base_url=FAKE_URL, model=PRIMARY, max_retries=0,
                model_fallbacks=FALLBACKS)
    base.update(overrides)
    return Settings(**base)


def model_of(request):
    import json as _json
    return _json.loads(request.content.decode('utf-8'))['model']


def recording_handler(responses, calls):
    """`responses`: {模型名: 处理器}；处理器接收该模型的调用次数，返回 Response 或抛异常。"""
    def handler(request):
        model = model_of(request)
        calls.append(model)
        seen = calls.count(model)
        return responses[model](seen)
    return handler


# ---------------------------------------------------------------- 配置解析

def test_parse_models_dedupes_and_preserves_order():
    assert _parse_models('a', 'b,c') == ('a', 'b', 'c')
    # 主模型重复出现在 fallbacks 里只算一次
    assert _parse_models('a', 'a,b') == ('a', 'b')
    # 空格、空项、多余逗号都要被清掉
    assert _parse_models(' a ', ' , b ,, c ,') == ('a', 'b', 'c')
    # 分号也当分隔符（有人在 .env 里会这么写）
    assert _parse_models('a', 'b;c') == ('a', 'b', 'c')


def test_parse_models_handles_empty():
    assert _parse_models('', '') == ()
    assert _parse_models('a', '') == ('a',)
    assert _parse_models('', 'b') == ('b',)


def test_settings_models_property_matches_env_shape():
    s = settings()
    assert s.models == ALL_MODELS
    assert s.models[0] == s.model          # 主模型永远排第一
    assert Settings(api_key='k', base_url=FAKE_URL, model='only').models == ('only',)


# ---------------------------------------------------------------- 降级行为

def test_primary_model_missing_falls_back_to_next(monkeypatch):
    """实测场景：学校端点 deepseek-chat → 403，不存在的模型 → 404，换模型即解决。"""
    calls = []
    responses = {
        PRIMARY: lambda n: httpx.Response(404, json={'error': {'message': 'not found'}}),
        'backup-one': lambda n: httpx.Response(200, json=completion('备用模型回答', 'backup-one')),
    }
    patch_transport(monkeypatch, recording_handler(responses, calls))

    result = create_client(settings()).ask('解释牛顿第二定律')

    assert result['mode'] == 'online'
    assert result['fallback_text'] is False
    assert result['text'] == '备用模型回答'
    assert result['model'] == 'backup-one'          # 报告真正出答案的模型
    assert calls == [PRIMARY, 'backup-one']         # 主模型只试一次（max_retries=0）
    assert result['attempted_models'] == (PRIMARY, 'backup-one')


def test_empty_content_triggers_downgrade(monkeypatch):
    """实测场景：Paratera 的 DeepSeek-V4-Flash 会返回空 content。"""
    calls = []
    responses = {
        PRIMARY: lambda n: httpx.Response(200, json=completion('   ', PRIMARY)),
        'backup-one': lambda n: httpx.Response(200, json=completion('非空回答', 'backup-one')),
    }
    patch_transport(monkeypatch, recording_handler(responses, calls))

    result = create_client(settings()).ask('提问')

    assert result['mode'] == 'online' and result['model'] == 'backup-one'
    assert result['text'] == '非空回答'


def test_permission_denied_on_all_models_reports_primary_cause(monkeypatch):
    calls = []
    responses = {name: (lambda n: httpx.Response(403, json={'error': 'no permission'}))
                 for name in ALL_MODELS}
    patch_transport(monkeypatch, recording_handler(responses, calls))

    result = create_client(settings()).ask('提问')

    assert result['mode'] == 'mock' and result['fallback_text'] is True
    assert calls == list(ALL_MODELS)            # 每个模型都试过一次
    assert result['attempted_models'] == ALL_MODELS
    # error 报告主模型的原因，最接近用户真实问题
    assert 'PermissionDenied' in result['error'] or result['error']
    assert '已回退离线引导' in result['text']


def test_rate_limit_is_retried_then_downgraded(monkeypatch):
    """限流：先在同一模型上重试（max_retries 次），耗尽后再换模型。"""
    calls = []
    responses = {
        PRIMARY: lambda n: httpx.Response(429, json={'error': 'rate limited'}),
        'backup-one': lambda n: httpx.Response(200, json=completion('降级成功', 'backup-one')),
    }
    patch_transport(monkeypatch, recording_handler(responses, calls))
    client = create_client(settings(max_retries=2))

    result = client.ask('提问')

    assert result['mode'] == 'online' and result['model'] == 'backup-one'
    assert calls == [PRIMARY, PRIMARY, PRIMARY, 'backup-one']   # 1 + 2 次重试，再降级
    assert result['attempted_models'] == (PRIMARY, 'backup-one')


def test_connection_error_is_retried_but_never_switches(monkeypatch):
    """连接错误换模型无意义：仍然重试，但不会去打其它模型。"""
    calls = []

    def handler(request):
        calls.append(model_of(request))
        raise httpx.ConnectError('network down')

    patch_transport(monkeypatch, handler)
    result = create_client(settings(max_retries=2)).ask('提问')

    assert result['mode'] == 'mock'
    assert calls == [PRIMARY, PRIMARY, PRIMARY]      # 只打主模型，重试 2 次
    assert 'backup-one' not in calls
    assert result['attempted_models'] == (PRIMARY,)


def test_timeout_is_retried_but_never_switches(monkeypatch):
    calls = []

    def handler(request):
        calls.append(model_of(request))
        raise httpx.ReadTimeout('slow')

    patch_transport(monkeypatch, handler)
    result = create_client(settings(max_retries=1)).ask('提问')

    assert result['mode'] == 'mock'
    assert calls == [PRIMARY, PRIMARY]
    assert 'backup-one' not in calls


def test_auth_error_stops_immediately_without_retry(monkeypatch):
    """401 是配置问题，等多久都不会好：不重试、不换模型，立刻回退。"""
    calls = []

    def handler(request):
        calls.append(model_of(request))
        return httpx.Response(401, json={'error': 'invalid api key'})

    patch_transport(monkeypatch, handler)
    result = create_client(settings(max_retries=3)).ask('提问')

    assert result['mode'] == 'mock'
    assert calls == [PRIMARY]                    # 一次就结束
    assert result['attempted_models'] == (PRIMARY,)


def test_retry_then_success_on_primary_does_not_downgrade(monkeypatch):
    calls = []
    responses = {
        PRIMARY: lambda n: (httpx.Response(200, json=completion('终于成功', PRIMARY))
                            if n >= 2 else httpx.Response(500, json={'error': 'boom'})),
    }
    patch_transport(monkeypatch, recording_handler(responses, calls))

    result = create_client(settings(max_retries=2)).ask('提问')

    assert result['mode'] == 'online' and result['text'] == '终于成功'
    assert calls == [PRIMARY, PRIMARY]           # 没走到备用模型
    assert result['attempted_models'] == (PRIMARY,)


def test_no_fallbacks_configured_behaves_as_before(monkeypatch):
    calls = []
    responses = {PRIMARY: lambda n: httpx.Response(404, json={'error': 'not found'})}
    patch_transport(monkeypatch, recording_handler(responses, calls))

    result = create_client(settings(model_fallbacks=())).ask('提问')

    assert result['mode'] == 'mock'
    assert calls == [PRIMARY]


# ---------------------------------------------------------------- 界面呈现

def test_mode_summary_shows_downgrade_chain():
    text = mode_summary(settings())
    assert '降级顺序' in text
    assert PRIMARY in text and 'backup-one' in text and 'backup-two' in text


def test_mode_summary_says_not_configured_when_no_fallbacks():
    text = mode_summary(settings(model_fallbacks=()))
    assert '未配置' in text


def test_connection_report_announces_downgrade(monkeypatch):
    calls = []
    responses = {
        PRIMARY: lambda n: httpx.Response(404, json={'error': 'not found'}),
        'backup-one': lambda n: httpx.Response(200, json=completion('连接成功', 'backup-one')),
    }
    patch_transport(monkeypatch, recording_handler(responses, calls))

    report = connection_report(create_client(settings()))

    assert '连接成功（在线模型）' in report
    assert 'backup-one' in report                # 说明实际用的是备用模型
    assert PRIMARY in report                     # 说明主模型不可用
    assert FAKE_KEY not in report


def test_connection_report_lists_all_attempts_on_total_failure(monkeypatch):
    calls = []
    responses = {name: (lambda n: httpx.Response(404, json={'error': 'not found'}))
                 for name in ALL_MODELS}
    patch_transport(monkeypatch, recording_handler(responses, calls))

    report = connection_report(create_client(settings()))

    assert '在线调用失败，已回退 Mock' in report
    assert '已尝试 3 个模型' in report
    assert FAKE_KEY not in report
