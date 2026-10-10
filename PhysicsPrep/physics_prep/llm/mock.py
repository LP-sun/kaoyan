"""离线 Mock 教师。

用途：
- 未配置 `GENAI_API_KEY` / `GENAI_BASE_URL` / `GENAI_MODEL` 时保证全部功能可用；
- 在线调用失败时作为回退，保证界面不会因为网络问题不可用。

Mock 输出永远标记 `mode='mock'`，界面据此提示“非模型推理”，
避免把模板文本误当作真实模型回答。
"""
from .prompts import ERROR_ANALYSIS_SYSTEM, TUTOR_SYSTEM_AFTER_SUBMIT, TUTOR_SYSTEM_BEFORE_SUBMIT

MOCK_PREFIX = '【Mock 教师，非模型推理】'

HINT_TEXT = (
    '先列出已知量、未知量与适用条件，再判断应该用守恒定律还是基本方程；'
    '注意边界条件与符号约定。请说明你卡在哪一步，我会按步骤追问。'
)

AFTER_SUBMIT_TEXT = (
    '你已提交本题。标准答案与推导请对照“查看解析”区域；'
    '重点检查：适用条件是否满足、受力或几何分析是否完整、单位与量纲是否一致。'
)

FULL_SOLUTION_TEXT = (
    '下方展开的解析来自本地题库（人工编写并核验），不是模型生成内容。'
    '模型只负责解释你的疑问，不会修改判分结果。'
)

ERROR_ANALYSIS_TEXT = (
    '可能原因：概念理解、公式适用条件或数学计算中的某一环节。'
    '仅凭最终答案无法确定具体错因，建议通过前置知识点的追问进一步诊断。'
)


class MockLLMClient:
    """与 `OfficialGenAIClient` 相同的 `ask` 接口，但完全离线且确定性。"""

    name = 'mock'

    def ask(self, prompt, system=''):
        text = self._select(system)
        # fallback_text 语义见 client.py 的返回契约：Mock 文本一律不是模型输出。
        return {'text': f'{MOCK_PREFIX}{text}', 'mode': 'mock', 'error': None, 'fallback_text': True}

    def _select(self, system):
        if system == ERROR_ANALYSIS_SYSTEM:
            return ERROR_ANALYSIS_TEXT
        if not system or system == TUTOR_SYSTEM_BEFORE_SUBMIT:
            return HINT_TEXT
        if system == TUTOR_SYSTEM_AFTER_SUBMIT:
            return AFTER_SUBMIT_TEXT
        return FULL_SOLUTION_TEXT

    def test_connection(self):
        return {'text': f'{MOCK_PREFIX}当前为离线 Mock 模式，未发起网络请求。',
                'mode': 'mock', 'error': None, 'fallback_text': True}

    def error_analysis(self, prompt):
        return self.ask(prompt, system=ERROR_ANALYSIS_SYSTEM)
