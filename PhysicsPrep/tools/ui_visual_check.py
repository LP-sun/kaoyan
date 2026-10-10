"""真实浏览器视觉检查：打开首页、完成一次答题、检查解析与诊断报告。

通过 Playwright 驱动已安装的 Chromium，逐页截图并做基本可读性断言：
- KaTeX 是否真的完成渲染（存在 .katex 节点）；
- 题目卡片是否溢出容器（scrollWidth 与 clientWidth 比较）；
- 窄屏（390px）下是否出现横向溢出；
- 作答前页面是否泄露标准答案或解析文本。

用法：
    python tools/ui_visual_check.py [base_url] [out_dir]
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:7861'
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else 'data/ui-check')
CHROMIUM = Path.home() / 'AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'

report = {'base': BASE, 'shots': [], 'checks': []}


def check(name, passed, detail=''):
    report['checks'].append({'name': name, 'passed': bool(passed), 'detail': str(detail)[:400]})
    print(('PASS  ' if passed else 'FAIL  ') + name + (f' :: {detail}' if detail else ''))


def shot(page, name, full=True):
    path = OUT / f'{name}.png'
    page.screenshot(path=str(path), full_page=full)
    report['shots'].append(str(path))
    print('shot  ', path)


def canvas_overflow(page):
    return page.evaluate("""() => {
      const de = document.documentElement;
      return {scrollW: de.scrollWidth, clientW: de.clientWidth};
    }""")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not CHROMIUM.exists():
        raise SystemExit(f'chromium not found: {CHROMIUM}')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(CHROMIUM), args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
        page.goto(BASE, wait_until='domcontentloaded', timeout=60000)
        # Gradio 会长期保持一个 websocket 连接，networkidle 永远不会触发；
        # 改为等待首屏统计卡出现，作为“应用已挂载”的信号。
        page.locator('.stat-card').first.wait_for(state='visible', timeout=60000)
        page.wait_for_timeout(2000)

        check('首页标题可见', page.locator('text=PhysicsPrep · 物理考研').first.is_visible())
        check('学习总览统计卡渲染', page.locator('.stat-card').count() >= 4,
              f"{page.locator('.stat-card').count()} cards")
        shot(page, '01-dashboard')

        # ---- 开始诊断（力学）
        page.get_by_role('tab', name=re.compile('开始诊断')).click()
        page.wait_for_timeout(800)
        page.locator('#quiz-meta').wait_for(state='visible', timeout=15000)
        # Gradio 5 的 Dropdown 是 input[role=listbox] + aria-label，展开后选项在 ul.options。
        subject = page.locator('input[role="listbox"][aria-label="科目"]').first
        subject.click()
        page.wait_for_timeout(1200)
        page.get_by_role('option', name='力学', exact=True).first.click()
        page.wait_for_timeout(1200)
        check('科目下拉可选择', subject.input_value().strip() == '力学', subject.input_value())
        page.locator('#start-btn').click()
        page.wait_for_timeout(4000)

        stem_text = page.locator('#question-card').inner_text()
        meta_text = page.locator('#quiz-meta').inner_text()
        check('题目卡片有正文', len(stem_text.strip()) > 15, stem_text[:80].replace('\n', ' '))
        check('元信息含题型与难度', '难度' in meta_text and '题型' in meta_text, meta_text[:120].replace('\n', ' '))
        katex = page.locator('#question-card .katex').count()
        check('KaTeX 公式已渲染', katex >= 1, f'{katex} katex nodes')
        shot(page, '02-question')

        # ---- 作答前不得泄露答案
        body = page.locator('body').inner_text()
        check('作答前未显示“标准答案”', '标准答案' not in body)
        check('作答前未显示“推导与检验”', '推导与检验' not in body)

        # ---- 选择题：选第一个选项后提交
        option_labels = page.locator('#quiz-options label')
        n_opts = option_labels.count()
        textbox_visible = page.locator('textarea[placeholder*="sqrt"]').count() > 0 and \
            page.locator('textarea[placeholder*="sqrt"]').first.is_visible()
        if n_opts > 0:
            check('选择题选项渲染', n_opts >= 2, f'{n_opts} options')
            option_labels.first.click()
            page.wait_for_timeout(400)
            page.get_by_role('button', name=re.compile('提交答案')).click()
            page.wait_for_timeout(3000)
        elif textbox_visible:
            page.locator('textarea[placeholder*="sqrt"]').first.fill('sqrt(2*g*h)')
            page.get_by_role('button', name=re.compile('提交答案')).click()
            page.wait_for_timeout(3500)
        else:
            check('存在可作答控件', False, 'no radio and no textbox')

        feedback = page.locator('#feedback-card').inner_text()
        check('提交后出现反馈', ('正确' in feedback or '巩固' in feedback or '确认' in feedback),
              feedback[:120].replace('\n', ' '))
        check('反馈含关联知识点', '关联知识点' in feedback)
        check('反馈含错因判断', '错因' in feedback)
        shot(page, '03-feedback')

        page.get_by_role('button', name=re.compile('查看解析')).click()
        page.wait_for_timeout(2000)
        solution = page.locator('#solution-card').inner_text()
        check('解析含标准答案', '标准答案' in solution, solution[:100].replace('\n', ' '))
        check('解析含推导与检验', '推导与检验' in solution)
        shot(page, '04-solution')

        # ---- 下一题不应残留上一题反馈
        page.get_by_role('button', name=re.compile('下一题')).click()
        page.wait_for_timeout(3000)
        feedback_after = page.locator('#feedback-card').inner_text().strip()
        check('切换到下一题后反馈被清空', feedback_after == '' or '标准答案' not in feedback_after,
              repr(feedback_after[:60]))
        new_stem = page.locator('#question-card').inner_text()
        check('下一题题干已更换', new_stem.strip()[:60] != stem_text.strip()[:60])

        # ---- 诊断报告
        page.get_by_role('button', name=re.compile('查看本轮诊断报告')).click()
        page.wait_for_timeout(2000)
        report_text = page.locator('text=诊断报告').first.inner_text()
        check('诊断报告可查看', '诊断报告' in report_text)
        shot(page, '05-report')

        # ---- 知识树
        page.get_by_role('tab', name=re.compile('知识树')).click()
        page.wait_for_timeout(2500)
        tree_text = page.locator('body').inner_text()
        check('知识树渲染四级结构', 'PHY-MECH' in tree_text and '前置知识' in tree_text)
        shot(page, '06-knowledge-tree')

        # ---- 错题与复习
        page.get_by_role('tab', name=re.compile('错题与复习')).click()
        page.wait_for_timeout(2500)
        check('错题页渲染', '到期复习' in page.locator('body').inner_text())
        shot(page, '07-wrong-answers')

        # ---- 设置页
        page.get_by_role('tab', name=re.compile('设置与备份')).click()
        page.wait_for_timeout(2000)
        settings_text = page.locator('body').inner_text()
        check('设置页显示模式说明', '当前模式' in settings_text)
        check('设置页不泄露完整密钥', 'GENAI_API_KEY=' not in settings_text)
        shot(page, '08-settings')

        # ---- 横向溢出（桌面）
        metrics = canvas_overflow(page)
        check('桌面无横向溢出', metrics['scrollW'] <= metrics['clientW'] + 2, json.dumps(metrics))

        # ---- 窄屏检查
        page.set_viewport_size({'width': 390, 'height': 844})
        page.wait_for_timeout(1500)
        page.get_by_role('tab', name=re.compile('开始诊断')).click()
        page.wait_for_timeout(2000)
        narrow = canvas_overflow(page)
        check('窄屏无横向溢出', narrow['scrollW'] <= narrow['clientW'] + 2, json.dumps(narrow))
        shot(page, '09-narrow-quiz')
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.get_by_role('tab', name=re.compile('学习总览')).click()
        page.wait_for_timeout(2000)
        # 统计与图表在进入标签页时可能是上一次的快照，必须能通过“刷新学习总览”更新。
        stale = page.evaluate("""() => Array.from(
            document.querySelectorAll('.js-plotly-plot .barlayer .point path'))
            .map(p => Math.round(p.getBBox().height))""")
        page.get_by_role('button', name=re.compile('刷新学习总览')).click()
        page.wait_for_timeout(3000)
        bars = page.evaluate("""() => Array.from(
            document.querySelectorAll('.js-plotly-plot .barlayer .point path'))
            .map(p => Math.round(p.getBBox().height))""")
        check('刷新后图表画出柱子', any(h > 2 for h in bars), f'before={stale} after={bars}')
        check('图表柱子数量等于 7 天', len(bars) == 7, f'{len(bars)} bars')
        stats_text = page.locator('.stats-grid').inner_text()
        check('刷新后今日作答题数已更新', '今日作答' in stats_text and '0\n' not in stats_text.split('今日作答')[1][:6],
              stats_text.replace('\n', ' ')[:80])
        page.screenshot(path=str(OUT / '10-dashboard-after.png'), full_page=True)
        report['shots'].append(str(OUT / '10-dashboard-after.png'))

        browser.close()

    passed = sum(1 for c in report['checks'] if c['passed'])
    report['summary'] = {'passed': passed, 'total': len(report['checks'])}
    (OUT / 'visual-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n== {passed}/{len(report['checks'])} checks passed ==")
    for c in report['checks']:
        if not c['passed']:
            print('  FAILED:', c['name'], c['detail'])
    return 0 if passed == len(report['checks']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
