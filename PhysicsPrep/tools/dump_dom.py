"""转储已渲染页面的关键 DOM 结构，用于确认可用的定位器。

用途：Gradio 版本升级会改动内部 DOM（例如 Dropdown 不再是 button[role=combobox]），
这个脚本把答题页的控件实际标签与 role 打印出来，避免视觉检查脚本靠猜测选择器。

用法：
    python tools/dump_dom.py [base_url]
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:7861'
CHROMIUM = Path.home() / 'AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'

PROBE = """() => {
  const out = {inputs: [], roles: {}};
  document.querySelectorAll('input, textarea, button, select').forEach((el, i) => {
    const r = el.getBoundingClientRect();
    out.inputs.push({
      idx: i, tag: el.tagName.toLowerCase(), type: el.type || '',
      role: el.getAttribute('role') || '',
      cls: (el.className || '').toString().slice(0, 80),
      aria: el.getAttribute('aria-label') || '',
      placeholder: el.getAttribute('placeholder') || '',
      visible: r.width > 0 && r.height > 0,
      text: (el.innerText || el.value || '').slice(0, 40)
    });
  });
  ['radio', 'checkbox', 'combobox', 'listbox', 'textbox', 'tab'].forEach(role => {
    out.roles[role] = document.querySelectorAll(`[role="${role}"]`).length;
  });
  out.tabs = Array.from(document.querySelectorAll('button[role="tab"]')).map(b => b.innerText.trim());
  return out;
}"""


def main():
    if not CHROMIUM.exists():
        raise SystemExit(f'chromium not found: {CHROMIUM}')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(CHROMIUM), args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.goto(BASE, wait_until='domcontentloaded', timeout=60000)
        page.locator('.stat-card').first.wait_for(state='visible', timeout=60000)
        page.wait_for_timeout(1500)

        print('=== TABS ===')
        print(page.evaluate("() => Array.from(document.querySelectorAll('button[role=\"tab\"]')).map(b=>b.innerText.trim())"))

        # 切到答题页
        page.get_by_role('tab', name='开始诊断').click()
        page.wait_for_timeout(2500)
        data = page.evaluate(PROBE)
        print('=== ROLE COUNTS (quiz tab) ===')
        print(json.dumps(data['roles'], ensure_ascii=False))
        print('=== VISIBLE CONTROLS ===')
        for item in data['inputs']:
            if item['visible']:
                print(json.dumps(item, ensure_ascii=False))
        page.screenshot(path='data/ui-check/_dom-quiz.png', full_page=True)
        browser.close()


if __name__ == '__main__':
    main()
