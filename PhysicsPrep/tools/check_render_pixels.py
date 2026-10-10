"""对截图做像素级检查，并与界面元素的实际尺寸对照。

因为当前会话模型不具备图像输入能力，视觉质量不能靠“看图”判断，
这里改为可量化的检查：
1. 用 Playwright 读取关键容器的 getBoundingClientRect，确认图表没有被压成 0 高度；
2. 用 PIL 统计图表区域的“墨水量”（非背景像素比例），判断是否空白；
3. 检查是否存在明显的布局异常（例如内容整体偏左、右侧大片空白）。

用法：
    python tools/check_render_pixels.py [base_url] [out_dir]
"""
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:7861'
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else 'data/ui-check')
CHROMIUM = Path.home() / 'AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'

report = {'checks': [], 'metrics': {}}


def check(name, passed, detail=''):
    report['checks'].append({'name': name, 'passed': bool(passed), 'detail': str(detail)[:300]})
    print(('PASS  ' if passed else 'FAIL  ') + name + (f' :: {detail}' if detail else ''))


def ink_ratio(image, box):
    """返回区域内与背景色差异明显的像素比例，以及主要颜色。"""
    crop = image.convert('RGB').crop(box)
    pixels = list(crop.getdata())
    if not pixels:
        return 0.0, []
    background = Counter(pixels).most_common(1)[0][0]
    inked = sum(1 for p in pixels if sum(abs(a - b) for a, b in zip(p, background)) > 45)
    return inked / len(pixels), Counter(pixels).most_common(3)


def main():
    if not CHROMIUM.exists():
        raise SystemExit(f'chromium not found: {CHROMIUM}')
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(CHROMIUM), args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.goto(BASE, wait_until='domcontentloaded', timeout=60000)
        page.locator('.stat-card').first.wait_for(state='visible', timeout=60000)
        page.wait_for_timeout(3500)  # 等 Plotly 画完

        # ---- 容器尺寸
        sizes = page.evaluate("""() => {
          const pick = (sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {w: Math.round(r.width), h: Math.round(r.height),
                    x: Math.round(r.x), y: Math.round(r.y)};
          };
          return {
            container: pick('.gradio-container'),
            hero: pick('.hero'),
            stats: pick('.stats-grid'),
            plot: pick('.js-plotly-plot') || pick('.plot-container'),
            svg: pick('.js-plotly-plot svg.main-svg'),
            bars: document.querySelectorAll('.js-plotly-plot .barlayer .point path').length,
            xticks: document.querySelectorAll('.js-plotly-plot .xtick text').length,
            yticks: document.querySelectorAll('.js-plotly-plot .ytick text').length,
            modebar: pick('.modebar'),
          };
        }""")
        report['metrics']['sizes'] = sizes
        print('sizes:', json.dumps(sizes, ensure_ascii=False))

        check('图表容器有实际高度', (sizes.get('plot') or {}).get('h', 0) > 100,
              json.dumps(sizes.get('plot')))
        check('图表 SVG 已挂载', (sizes.get('svg') or {}).get('w', 0) > 100, json.dumps(sizes.get('svg')))
        check('存在柱状图数据点', sizes.get('bars', 0) >= 7, f"bars={sizes.get('bars')}")
        check('坐标轴刻度已渲染', sizes.get('xticks', 0) >= 3, f"xticks={sizes.get('xticks')}")

        # ---- 内容是否居中
        container = sizes.get('container') or {}
        stats = sizes.get('stats') or {}
        if container and stats:
            left_gap = stats['x']
            right_gap = container['w'] - (stats['x'] + stats['w'])
            report['metrics']['gaps'] = {'left': left_gap, 'right': right_gap}
            print('stats gaps:', left_gap, right_gap)
            check('内容相对居中（左右边距差 < 容器宽 12%）', abs(left_gap - right_gap) < container['w'] * 0.12,
                  f"left={left_gap} right={right_gap} container={container['w']}")

        page.screenshot(path=str(OUT / 'pixel-dashboard.png'), full_page=True)
        browser.close()

    # ---- 像素级墨水量
    image = Image.open(OUT / 'pixel-dashboard.png')
    report['metrics']['image'] = {'w': image.width, 'h': image.height}
    plot = sizes.get('plot')
    if plot:
        box = (max(0, plot['x']), max(0, plot['y']),
               min(image.width, plot['x'] + plot['w']), min(image.height, plot['y'] + plot['h']))
        ratio, top = ink_ratio(image, box)
        report['metrics']['plot_ink'] = {'box': box, 'ratio': round(ratio, 5),
                                         'top_colors': [[list(c), n] for c, n in top]}
        print('plot ink ratio:', round(ratio, 5), 'box', box)
        check('图表区域不是空白（墨水比例 > 0.5%）', ratio > 0.005, f'ratio={ratio:.5f}')

    (OUT / 'pixel-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['passed'])
    print(f"\n== {passed}/{len(report['checks'])} pixel checks passed ==")
    for c in report['checks']:
        if not c['passed']:
            print('  FAILED:', c['name'], c['detail'])
    return 0 if passed == len(report['checks']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
