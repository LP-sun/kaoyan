"""用真实视觉模型对界面截图做独立验收。

背景：本会话主模型不支持图像输入，因此“界面观感”一直无法由我确认。
本脚本把真实截图交给一个**具备视觉能力**的模型，让它只描述实际看到的像素内容，
再由我对照这些描述检查排版问题。

安全约定：
- 密钥只从 DSH 本机凭据文件读取，**不打印**、不写入项目任何文件；
- 只上传 `data/ui-check/` 下本项目自己生成的截图，不上传教材、题库或学习记录。

用法：
    python tools/vision_review.py [截图目录] [输出目录]
"""
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

CRED = Path.home() / '.dsh' / '.credentials.yaml'
PARATERA_BASE = 'https://llmapi.paratera.com'
VISION_MODEL = 'GLM-4.6V'
FALLBACK_MODELS = ['GLM-4.5V', 'GLM-4V-Plus-0111', 'ERNIE-4.5-Turbo-VL-32K']

# 每张图配一个中性说明，只交代“这是什么页面”，不暗示任何缺陷，
# 避免把结论喂给评审模型。
CAPTIONS = {
    '01-dashboard.png': '学习总览首页：顶部标题、统计卡片、最近七天作答图表。',
    '02-question.png': '答题页：中间是一道物理题的题卡，含公式与作答控件。',
    '03-feedback.png': '提交答案后的反馈区域。',
    '04-solution.png': '展开解析后的页面。',
    '05-report.png': '本轮诊断报告页面。',
    '06-knowledge-tree.png': '知识树页面，展示多层级的考点结构。',
    '07-wrong-answers.png': '错题与复习页面。',
    '08-settings.png': '设置与备份页面。',
    '09-narrow-quiz.png': '窄屏（手机宽度约 390px）下的答题页。',
    '10-dashboard-after.png': '刷新后的学习总览首页。',
}

PROMPT = """这是一张中文学习类网页应用的真实截图（页面用途：{caption}）。

请只描述你**实际看到**的内容，不要推测、不要补充你没看到的东西。按以下格式回答：

1. 整体布局：几栏？最大宽度大约占屏幕多少？内容是否居中？
2. 可见的中文文字：把主要标题与按钮文字**原样抄写**出来（你能辨认的都要写）。
3. 结构元素：统计卡片几个？图表几个？表格几个？输入框几个？按钮几个？
4. 数学公式：是否看到 LaTeX 渲染出的数学符号（如分式、希腊字母 sin/theta/m）？举例。
5. 配色与可读性：主色调是什么？文字与背景对比是否足够？字号看起来是否舒适？
6. 排版问题：是否存在以下任何一项——文字溢出容器、元素重叠、大片空白区域、
   乱码或“豆腐块”方框、图片/图表加载失败、横向滚动条、文字被截断？请明确指出位置。

如果某一项你无法从图中判断，直接写“无法判断”，不要编造。"""


def load_key():
    if not CRED.exists():
        return None
    for line in CRED.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if stripped.startswith('PARATERA_API_KEY:'):
            return stripped.split(':', 1)[1].strip()
    return None


def ask_vision(key, model, image_path, caption, prompt=None, max_tokens=1200):
    b64 = base64.b64encode(image_path.read_bytes()).decode('ascii')
    response = httpx.post(
        PARATERA_BASE + '/chat/completions',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        json={
            'model': model,
            'max_tokens': max_tokens,
            'messages': [{'role': 'user', 'content': [
                {'type': 'text', 'text': (prompt or PROMPT).format(caption=caption)},
                {'type': 'image_url',
                 'image_url': {'url': f'data:image/png;base64,{b64}'}},
            ]}],
        },
        timeout=240.0)
    return response


def main():
    shots_dir = Path(sys.argv[1] if len(sys.argv) > 1 else 'data/ui-check')
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else 'data/vision-review')
    # GLM-4.6V 是推理型模型：预算不足时会把 token 全用在内部推理上，
    # content 直接返回空字符串（曾因此让 4 张图看起来“无描述”）。默认给足。
    budget = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
    out_dir.mkdir(parents=True, exist_ok=True)

    key = load_key()
    if not key:
        print('未找到 PARATERA_API_KEY，无法进行视觉验收。')
        return 1
    print(f'密钥已获取（长度 {len(key)}，末四位 ****{key[-4:]}）  预算 max_tokens={budget}')

    images = sorted(shots_dir.glob('*.png'))
    if not images:
        print(f'{shots_dir} 下没有截图，请先运行 tools/ui_visual_check.py。')
        return 1

    results = {}
    used_model = None
    for model in [VISION_MODEL] + FALLBACK_MODELS:
        probe = ask_vision(key, model, images[0], CAPTIONS.get(images[0].name, '网页截图'),
                           max_tokens=budget)
        if probe.status_code == 200:
            used_model = model
            print(f'视觉模型可用: {model}')
            results[images[0].name] = probe.json()['choices'][0]['message']['content']
            break
        print(f'{model} 不可用: HTTP {probe.status_code} {probe.text[:120]}')
    if not used_model:
        print('所有候选视觉模型均不可用。')
        return 1

    for image in images[1:]:
        caption = CAPTIONS.get(image.name, '网页截图')
        started = time.time()
        response = ask_vision(key, used_model, image, caption, max_tokens=budget)
        if response.status_code != 200:
            print(f'{image.name}: 失败 HTTP {response.status_code} {response.text[:140]}')
            continue
        body = response.json()
        text = (body['choices'][0]['message'].get('content') or '').strip()
        if not text:
            print(f'{image.name}: content 为空（finish={body["choices"][0].get("finish_reason")}），'
                  f'预算可能不足，已跳过')
            continue
        results[image.name] = text
        print(f'{image.name}: 完成（{time.time() - started:.1f}s，{len(text)} 字符）')

    report = out_dir / 'vision-review.json'
    report.write_text(json.dumps({'model': used_model, 'results': results},
                                 ensure_ascii=False, indent=2), encoding='utf-8')

    markdown = [f'# 视觉验收报告（模型：`{used_model}`）', '',
                '> 由具备图像输入能力的模型对 `data/ui-check/` 下的真实截图逐张描述。',
                '> 本文件是模型的原始观察记录，便于人工复核。', '']
    for name, text in results.items():
        markdown += [f'## {name}', '', f'*页面说明：{CAPTIONS.get(name, "网页截图")}*', '', text, '']
    (out_dir / 'vision-review.md').write_text('\n'.join(markdown), encoding='utf-8')

    print(f'\n报告已写出：{report}')
    print(f'可读版本：{out_dir / "vision-review.md"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
