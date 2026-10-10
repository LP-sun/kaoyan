"""只截取「设置与备份」页，用于人工/视觉验收在线模式与降级链的展示。

会点击一次「测试模型连接」并把结果留在页面上（真实网络调用）。
用法：
    python tools/shot_settings.py http://127.0.0.1:7861 data/ui-check
"""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:7861'
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else 'data/ui-check')
OUT.mkdir(parents=True, exist_ok=True)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        page.goto(BASE, wait_until='domcontentloaded')
        page.wait_for_selector('.stat-card', timeout=30000)

        page.get_by_role('tab', name=re.compile('设置与备份')).click()
        page.wait_for_timeout(2500)

        page.screenshot(path=str(OUT / '11-settings-online.png'), full_page=True)

        summary = page.inner_text('body')
        for token in ('GenAI 在线', '降级顺序', 'GenAI 在线（失败时自动回退 Mock）'):
            print(('  有  ' if token in summary else '  无  ') + token)
        print('  降级链片段:', [ln.strip() for ln in summary.splitlines()
                              if '降级顺序' in ln or '→' in ln][:2])

        print('  正在测试模型连接（真实网络调用）...')
        page.get_by_role('button', name=re.compile('测试模型连接')).click()
        for _ in range(50):
            page.wait_for_timeout(3000)
            text = page.locator('#connection-result').inner_text().strip()
            if '连接成功' in text or '已回退' in text or 'Mock 模式' in text:
                break
        page.screenshot(path=str(OUT / '12-connection-result.png'), full_page=True)
        print('  连接结果:', text.replace('\n', ' ')[:200])

        browser.close()
    print(f'\n截图: {OUT / "11-settings-online.png"}')
    print(f'      {OUT / "12-connection-result.png"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
