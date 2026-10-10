"""统一的大模型客户端抽象。

两个实现：

- `OfficialGenAIClient`：上海科技大学 GenAI 的 OpenAI 兼容 Chat Completions 接口；
- `MockLLMClient`：离线确定性教师，保证没有密钥时全部核心功能可用。

安全与稳定性约定：
- 密钥只从环境变量 / `.env` 读取，不写入代码，也不进入日志与返回值；
- 错误处理只保留异常类别名，不打印请求、URL、响应正文或认证头；
- 调用带超时、指数退避、并发上限，避免无意义的重复请求；
- 在线失败时回退到 Mock，并在返回值里标记 `error` 与 `fallback_text`。

模型降级
--------

`GENAI_MODEL` 是主模型，`GENAI_MODEL_FALLBACKS` 是逗号分隔的备用模型。
主模型失败且**错误类型表明换模型有意义**时，按顺序尝试下一个模型。

- 值得换模型：模型不存在、无权限、请求被拒、限流、返回空内容。
  实测依据：学校端点 `deepseek-chat` 返回 403、不存在的模型返回 404，
  这两种都是换模型即可解决；Paratera 的 `DeepSeek-V4-Flash` 会返回空内容。
- 不值得换模型：认证失败（401/402）、连接失败、超时、代理错误。
  这类问题换模型必然同样失败，只会多打一次付费请求，因此直接回退 Mock。

同一模型内部仍按 `GENAI_MAX_RETRIES` 做指数退避重试；
换模型之间只做 `SWITCH_MODEL_DELAY_SECONDS` 的短暂停顿。

`ask()` 的返回契约：

| 键 | 含义 |
| --- | --- |
| `text` | 回答文本。**可能是真实模型输出，也可能是 Mock 替换内容** |
| `mode` | `'online'` = 文本来自模型；`'mock'` = 文本来自本地 Mock |
| `error` | `None`，或**主模型**失败的异常类别名（最接近真实原因） |
| `last_error` | 仅当最后失败的模型与主模型不同且原因不同时才出现 |
| `fallback_text` | `True` 表示 `text` 是失败后替换的内容，调用方不得当作模型输出 |
| `model` | 真正给出这段文本的模型 ID；`mode='mock'` 时为 `None` |
| `attempted_models` | 实际尝试过的模型顺序（便于排查降级发生在哪一步） |

调用方判断“是否真的连通”必须看 `mode`，不能只看有没有拿到文本。

本模块**不**假定学校 API 支持原生 Tool Calling 或 JSON Schema 结构化输出，
只使用标准 Chat Completions 文本补全。
"""
import threading
import time
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from ..config import Settings
from .mock import MockLLMClient
from .prompts import CONNECTION_TEST_PROMPT, CONNECTION_TEST_SYSTEM, ERROR_ANALYSIS_SYSTEM

__all__ = ['LLMClient', 'MockLLMClient', 'OfficialGenAIClient', 'create_client', 'LLMUnavailable']

MAX_PROMPT_CHARS = 6000
MAX_RESPONSE_TOKENS = 1024
# 换模型前的短暂停顿：给按 key 计算的限流一点恢复时间，但不做长退避。
SWITCH_MODEL_DELAY_SECONDS = 1.0

# 这些异常说明“换任何模型都会失败”，所以**不降级**：认证失败、连不上、代理错误。
# 注意它们**仍然会按 max_retries 重试**（瞬时限流/抖动可以靠重试恢复，这是原有行为），
# 只是不会再去打一遍其它模型。
_NO_SWITCH_CATEGORIES = {
    'AuthenticationError',
    'APIConnectionError',
    'ConnectError',
    'ProxyError',
    'RemoteProtocolError',
    # 超时同理：同一模型重试有意义（端点可能只是慢），换模型没意义。
    'APITimeoutError',
    'ConnectTimeout',
    'ReadTimeout',
    'WriteTimeout',
    'PoolTimeout',
    'TimeoutException',
}
# 即便类别名不认识，HTTP 状态码也能判断：401 认证失败、402 欠费。
# 这两种连重试都没意义（不会自己变好），立刻回退。
_HARD_STOP_STATUS = {401, 402}


def _hard_stop(exc, category):
    """这个异常是否连重试都不必做（配置性错误，等多久都不会好）。"""
    if category == 'AuthenticationError':
        return True
    status = getattr(exc, 'status_code', None)
    return isinstance(status, int) and status in _HARD_STOP_STATUS


def _worth_switching_model(category):
    """当前模型重试耗尽后，换下一个模型是否有意义。

    保守原则：**拿不准就不换**（换模型会再打一次付费请求）。
    已知无意义的是连接类与超时类；其余如模型不存在、无权限、请求被拒、
    限流、空内容，实测都确实能通过换模型解决。
    """
    return category not in _NO_SWITCH_CATEGORIES


class LLMUnavailable(RuntimeError):
    """在线客户端无法构造（配置或地址不合法）。"""


class LLMClient(ABC):
    """所有客户端的最小接口。判分与学习记录不依赖本接口。"""

    name = 'base'

    @abstractmethod
    def ask(self, prompt, system=''):
        """返回 {'text': str, 'mode': 'mock'|'online', 'error': str|None}。"""

    def test_connection(self):
        return self.ask(CONNECTION_TEST_PROMPT, system=CONNECTION_TEST_SYSTEM)

    def error_analysis(self, prompt):
        """错因分析只作为建议；调用方必须保留“可能原因”的措辞。"""
        return self.ask(prompt, system=ERROR_ANALYSIS_SYSTEM)


class OfficialGenAIClient(LLMClient):
    """OpenAI 兼容 Chat Completions 客户端。"""

    name = 'genai'
    # 限制并发，避免界面连点造成重复计费/限流。
    _semaphore = threading.BoundedSemaphore(2)

    def __init__(self, settings=None, transport=None, sleep=time.sleep):
        self.settings = settings or Settings.from_env()
        self.sleep = sleep
        parsed = urlparse(self.settings.base_url or '')
        if parsed.scheme != 'https' or not parsed.hostname:
            raise LLMUnavailable('GenAI API Address 必须是有效的 HTTPS 地址。')
        if not self.settings.model:
            raise LLMUnavailable('请配置模型 ID（GENAI_MODEL）。')
        from openai import OpenAI
        import httpx
        # 关掉 SDK 自带重试，退避策略由本模块统一控制。
        self.client = OpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
            timeout=self.settings.timeout,
            max_retries=0,
            http_client=httpx.Client(timeout=self.settings.timeout, transport=transport, trust_env=False),
        )

    def ask(self, prompt, system=''):
        if not isinstance(prompt, str) or not prompt.strip():
            return {'text': '请输入问题。', 'mode': 'local', 'error': 'empty_input'}
        if len(prompt) > MAX_PROMPT_CHARS:
            return {'text': f'问题超过 {MAX_PROMPT_CHARS} 字符，请缩短后重试。', 'mode': 'local', 'error': 'input_limit'}

        messages = [
            {'role': 'system', 'content': system or '你是物理教师。给出适用条件，不猜测学生错因。'},
            {'role': 'user', 'content': prompt},
        ]
        models = self.settings.models
        first_error = None          # 主模型的失败原因，最接近用户的真实问题
        last_error = None           # 最后一个模型的失败原因
        attempted = []

        with self._semaphore:
            for index, model in enumerate(models):
                fallback_hop = index > 0
                for attempt in range(self.settings.max_retries + 1):
                    try:
                        response = self.client.chat.completions.create(
                            model=model, messages=messages, max_tokens=MAX_RESPONSE_TOKENS)
                        text = ''
                        if response.choices:
                            text = response.choices[0].message.content or ''
                        if not text.strip():
                            # 空内容是**模型特定**的问题（实测 DeepSeek-V4-Flash 会这样），
                            # 所以虽然归在“可换模型”一类，也要先在同模型上重试。
                            raise ValueError('模型返回空内容')
                        return {'text': text, 'mode': 'online', 'error': None,
                                'fallback_text': False, 'model': model,
                                'attempted_models': tuple(attempted + [model])}
                    except Exception as exc:  # 只保留异常类别，不泄露请求细节
                        category = type(exc).__name__
                        if first_error is None:
                            first_error = category
                        last_error = category
                        if _hard_stop(exc, category):
                            # 认证失败、连不上这类问题，重试和换模型都没用。
                            attempted.append(model)
                            return self._offline(prompt, system, first_error, attempted)
                        if attempt < self.settings.max_retries:
                            # 同一模型重试：等久一点，让瞬时限流有机会恢复。
                            self.sleep(min(8, 2 ** attempt))
                attempted.append(model)
                if index + 1 < len(models) and _worth_switching_model(last_error):
                    # 换模型：等短一点。实测这里正是限流后的有效出路。
                    self.sleep(SWITCH_MODEL_DELAY_SECONDS)
                else:
                    break

        return self._offline(prompt, system, first_error, attempted, last_error)

    def _offline(self, prompt, system, category, attempted, last_error=None):
        """所有模型都失败 → 回退离线教师，界面仍然可用。

        必须标记 `fallback_text=True`：`text` 是替换内容，不是模型输出。
        """
        fallback = MockLLMClient().ask(prompt, system)
        fallback['error'] = category
        fallback['fallback_text'] = True
        fallback['model'] = None
        fallback['attempted_models'] = tuple(attempted)
        if last_error and last_error != category:
            fallback['last_error'] = last_error
        detail = category if not last_error or last_error == category else f'{category} → {last_error}'
        fallback['text'] = (f'在线调用失败（{detail}），已回退离线引导；'
                            f'固定题库与判分不受影响。\n{fallback["text"]}')
        return fallback



def create_client(settings=None):
    """按配置返回客户端；缺配置或地址非法时回退 Mock，绝不抛异常给界面。"""
    settings = settings or Settings.from_env()
    if settings.effective_mock:
        return MockLLMClient()
    try:
        return OfficialGenAIClient(settings)
    except LLMUnavailable:
        return MockLLMClient()
