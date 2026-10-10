"""针对疑点的定向视觉复核。

总览式描述容易漏掉细节（视觉模型只写下“图表 1 个”），因此对两个关键疑点单独提问：

A. 首页图表到底画出了什么？（此前曾出现“坐标轴空白、柱子高度为 0”的问题）
B. 窄屏下是否真的没有横向溢出与控件截断？

这两个问题都必须靠**看图**回答，DOM 断言只能间接证明。

用法：
    python tools/vision_spotcheck.py [截图目录]
"""
import base64
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vision_review import PARATERA_BASE, load_key  # noqa: E402

MODEL = 'GLM-4.6V'

CHART_Q = """这是一张中文网页的“学习总览”截图。请**只看图表区域**回答问题：

1. 图表里有柱子（竖条）吗？数一数有几根。
2. 这些柱子看起来是高矮不同，还是全部贴着底轴几乎为零高度？
3. 图表的横轴标了什么文字或标签？
4. 图表里有没有折线、点或其它图形？
5. 图表区域是否出现大片空白（即只有坐标轴、没有数据）？
6. 图表的标题文字是什么？

只回答这 6 点，每点一句话。看不清就说“看不清”。"""

NARROW_Q = """这是一张手机窄屏（约 390 像素宽）的中文网页截图。请回答：

1. 页面有没有横向滚动条，或者任何内容被右边缘切断？
2. 顶部导航标签是否换行或被截断？你能看到哪几个标签？
3. 题目文本、输入框、按钮是否完整显示、没有被压扁或重叠？
4. 表格或代码块有没有溢出容器？
5. 文字大小在这个宽度下是否仍然可读？
6. 有没有元素重叠或互相遮挡？

只回答这 6 点，每点一句话。看不清就说“看不清”。"""


def ask(key, image_path, question):
    b64 = base64.b64encode(image_path.read_bytes()).decode('ascii')
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
    out = Path('data/vision-review/spotcheck.json')
    key = load_key()
    if not key:
        print('未找到 PARATERA_API_KEY')
        return 1

    targets = [
        ('01-dashboard.png', 'A 首页图表', CHART_Q),
        ('10-dashboard-after.png', 'A 刷新后图表', CHART_Q),
        ('09-narrow-quiz.png', 'B 窄屏排版', NARROW_Q),
    ]
    results = {}
    for name, label, question in targets:
        path = shots / name
        if not path.exists():
            print(f'{label}: {name} 不存在，跳过')
            continue
        response = ask(key, path, question)
        if response.status_code != 200:
            print(f'{label}: HTTP {response.status_code} {response.text[:140]}')
            continue
        body = response.json()
        text = (body['choices'][0]['message'].get('content') or '').strip()
        print(f'\n===== {label}（{name}）=====')
        print(text if text else '<空响应>')
        results[label] = {'file': name, 'answer': text}

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n已写出 {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
