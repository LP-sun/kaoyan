"""对设置页截图做定向视觉复核（看不清就等于没验收）。

针对 `11-settings-online.png`（在线模式 + 降级链）与
`12-connection-result.png`（连接测试结果）提问。

用法：
    python tools/vision_shotcheck_settings.py [截图目录]
"""
import base64
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vision_review import PARATERA_BASE, load_key  # noqa: E402

MODEL = 'GLM-4.6V'

QUESTIONS = {
    '11-settings-online.png': """这是一张中文网页应用「设置与备份」页的真实截图。请只回答：

1. 页面上是否出现「GenAI 在线」字样？原样抄出你看到的那一行。
2. 是否有「降级顺序」这一行？把后面的模型名按顺序抄出来。
3. 页面上是否有任何像 API 密钥的完整字符串（长串字母数字）？有就说有，没有就说没有。
4. 文字有没有溢出容器、重叠、被截断或出现豆腐块方框？
5. 整体排版是否整齐？字号是否舒适？

每点一句话。看不清就说看不清。""",
    '12-connection-result.png': """这是一张中文网页应用的「设置与备份」页截图，用户刚点过「测试模型连接」。请只回答：

1. 连接测试的结果区域写了什么？把主要文字抄出来。
2. 结果是「连接成功」还是「失败回退」？
3. 有没有提到某个具体的模型名？抄出来。
4. 结果区域有没有排版问题（溢出、重叠、截断、乱码）？

每点一句话。看不清就说看不清。""",
}


def ask(key, path, question):
    b64 = base64.b64encode(path.read_bytes()).decode('ascii')
    response = httpx.post(
        PARATERA_BASE + '/chat/completions',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        json={'model': MODEL, 'max_tokens': 4000,
              'messages': [{'role': 'user', 'content': [
                  {'type': 'text', 'text': question},
                  {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}},
              ]}]},
        timeout=300.0)
    return response


def main():
    shots = Path(sys.argv[1] if len(sys.argv) > 1 else 'data/ui-check')
    key = load_key()
    if not key:
        print('未找到 PARATERA_API_KEY，跳过视觉复核。')
        return 1
    for name, question in QUESTIONS.items():
        path = shots / name
        if not path.exists():
            print(f'{name}: 不存在，跳过')
            continue
        response = ask(key, path, question)
        if response.status_code != 200:
            print(f'{name}: HTTP {response.status_code} {response.text[:140]}')
            continue
        text = (response.json()['choices'][0]['message'].get('content') or '').strip()
        print(f'\n===== {name} =====')
        print(text if text else '<空响应>')
    return 0


if __name__ == '__main__':
    sys.exit(main())
