"""用 `fastgpt-physics-lab/env/.env` 里已有的 GENAI_* 凭据验证 PhysicsPrep 在线模式。

这是"借用已有凭据"的验证：凭据来自同工作区内的另一个项目，不复制进 PhysicsPrep、
不打印、不写进 PhysicsPrep 仓库。

本脚本先做纯客户端层验证（不启动服务），确认 PhysicsPrep 自己的
`OfficialGenAIClient` 能在这套配置下真正连通并拿到模型回答。

用法：
    python tools/verify_with_lab_env.py [lab_env_path]
"""
import sys
from pathlib import Path

LAB_ENV = Path(sys.argv[1] if len(sys.argv) > 1 else
               r'C:\Users\Lenovo\Desktop\考研专业课\fastgpt-physics-lab\env\.env')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from physics_prep.config import Settings          # noqa: E402
from physics_prep.llm.client import create_client  # noqa: E402
from physics_prep.ui.settings import connection_report, mode_summary  # noqa: E402

KEYS = ('GENAI_API_KEY', 'GENAI_BASE_URL', 'GENAI_MODEL', 'GENAI_MODEL_FALLBACKS')


def load_lab_genai(path):
    """从 lab 的 .env 读取 GENAI_* 配置。只返回值，不打印。"""
    found = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        name, _, value = stripped.partition('=')
        name = name.strip()
        if name in KEYS:
            found[name] = value.strip().strip('"').strip("'")
    return found


def mask(value):
    if not value:
        return '<空>'
    return f'len={len(value)} ****{value[-4:]}'


def main():
    if not LAB_ENV.exists():
        print(f'找不到 {LAB_ENV}')
        return 1
    print(f'凭据来源: {LAB_ENV}')
    config = load_lab_genai(LAB_ENV)
    for name in KEYS:
        print(f'  {name:24s} {mask(config.get(name))}')

    settings = Settings(
        api_key=config.get('GENAI_API_KEY', ''),
        base_url=config.get('GENAI_BASE_URL', ''),
        model=config.get('GENAI_MODEL', ''),
        timeout=60,
        max_retries=2,
    )
    print(f'\nSettings.effective_mock = {settings.effective_mock}')
    if settings.effective_mock:
        print('配置不完整（缺 KEY / BASE_URL / MODEL 之一），将是 Mock 模式。')
        return 1

    client = create_client(settings)
    print(f'客户端实现: {getattr(client, "name", type(client).__name__)}')

    print('\n--- 模式摘要 ---')
    print(mode_summary(settings, client))

    print('\n--- 测试模型连接（真实网络）---')
    report = connection_report(client)
    print(report)
    online_ok = '连接成功（在线模型）' in report

    print('\n--- 真实问答（走 PhysicsPrep 的提示词与客户端）---')
    from physics_prep.llm.prompts import tutor_system
    result = client.ask(
        '一道题：质量 m>0 的物块在光滑斜面上由静止下滑，求加速度。'
        '请只回答应该使用哪条定律，不要给出最终答案。',
        system=tutor_system(after_submit=False, full_solution=False))
    print(f"mode={result['mode']}  error={result['error']}  fallback={result.get('fallback_text')}")
    print(f"回答: {result['text'][:300]}")
    answered = result['mode'] == 'online' and not result.get('fallback_text')

    print('\n=== 结论 ===')
    print(f"连接测试在线成功: {online_ok}")
    print(f"真实问答来自模型: {answered}")
    if online_ok and answered:
        print('PhysicsPrep 可以直接使用这套已有凭据。')
        return 0
    print('这套配置未能让 PhysicsPrep 在线工作，需要排查。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
