"""验证“配置了合法 GenAI 但端点不可达”时的真实启动路径与优雅回退。

这是唯一无法用单元测试替代的一环：`.env` 的加载、`app.py` 的真实启动、
界面“设置与备份”页在浏览器里报告的模式与失败原因。

由于环境没有学校真实凭据，这里用一个**格式合法但不可达**的 HTTPS 地址，
验证的不是“能连上”，而是“配了在线但连不上时，程序不崩、明确告知、并回退 Mock”。

用法：
    python tools/e2e_env_fallback_check.py [base_url] [server_workdir]
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:7863'
WORKDIR = Path(sys.argv[2] if len(sys.argv) > 2 else '.').resolve()
PORT = int(BASE.rstrip('/').rsplit(':', 1)[-1])
ENV_FILE = WORKDIR / '.env'
BACKUP = WORKDIR / '.env.e2e-backup'

failures = []


def check(name, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + name + (f' :: {detail}' if detail else ''))
    if not ok:
        failures.append(name)


def port_pid(port):
    out = subprocess.run(['netstat', '-ano', '-p', 'TCP'], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == 'LISTENING' and parts[1].endswith(f':{port}'):
            try:
                return int(parts[4])
            except ValueError:
                continue
    return None


def stop_server():
    pid = port_pid(PORT)
    if pid:
        subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
    time.sleep(3)


def start_server():
    env = dict(os.environ)
    env['PHYSICSPREP_PORT'] = str(PORT)
    env['PHYSICSPREP_DB_PATH'] = str(WORKDIR / 'data' / 'e2e-env' / 'study.sqlite3')
    env['PHYSICSPREP_OPEN_BROWSER'] = 'false'
    log = WORKDIR / 'data' / 'e2e-env' / 'server.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, 'ab') as handle:
        subprocess.Popen([str(WORKDIR / '.venv' / 'Scripts' / 'python.exe'), 'app.py'],
                         cwd=str(WORKDIR), env=env, stdout=handle, stderr=handle)
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + '/', timeout=2)
            time.sleep(2)
            return True
        except Exception:
            time.sleep(1)
    return False


print(f'== 目标：{BASE}  WORKDIR：{WORKDIR} ==')
stop_server()

# 备份用户可能已有的 .env，确保无论脚本如何结束都还原
had_env = ENV_FILE.exists()
if had_env:
    BACKUP.write_bytes(ENV_FILE.read_bytes())

try:
    # 格式合法、但域名不可达的地址；模型 ID 也是明显的占位值。
    ENV_FILE.write_text(
        'GENAI_API_KEY=sk-e2e-placeholder-not-a-real-key\n'
        'GENAI_BASE_URL=https://genai.invalid.example.edu/v1\n'
        'GENAI_MODEL=e2e-placeholder-model\n'
        'GENAI_TIMEOUT=5\n'
        'GENAI_MAX_RETRIES=1\n'
        'APP_MOCK_MODE=false\n',
        encoding='utf-8')
    check('已写入临时 .env（含在线配置）', ENV_FILE.exists())

    check('服务以在线配置启动成功', start_server())

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.goto(BASE, wait_until='domcontentloaded')
        page.wait_for_selector('.stat-card', timeout=30000)

        # 核心功能在“配了在线但连不上”时仍必须可用
        check('首页正常渲染', page.locator('.stat-card').count() >= 4)

        page.get_by_role('tab', name=re.compile('设置与备份')).click()
        page.wait_for_timeout(2000)
        settings_text = page.locator('body').inner_text()
        check('设置页报告为 GenAI 在线模式', 'GenAI 在线' in settings_text)
        check('设置页显示占位模型 ID', 'e2e-placeholder-model' in settings_text)
        check('设置页不回显 API Key', 'sk-e2e-placeholder-not-a-real-key' not in settings_text,
              '密钥未出现在页面文本中')

        page.get_by_role('button', name=re.compile('测试模型连接')).click()
        page.wait_for_timeout(15000)
        # 只看连接结果区域，避免整页文本里任何一个 “Mock” 字样让断言假通过。
        result = page.locator('#connection-result').inner_text()
        check('连接失败后明确报告已回退 Mock', '已回退 Mock' in result,
              result.replace('\n', ' ')[:140])
        check('报告了失败原因类别', 'Error' in result or 'Timeout' in result,
              result.replace('\n', ' ')[:140])
        check('未把 Mock 伪装成在线成功', '连接成功（在线模型）' not in result)

        # 判分功能不受在线失败影响
        page.get_by_role('tab', name=re.compile('开始诊断')).click()
        page.wait_for_timeout(1500)
        page.locator('#start-btn').click()
        page.wait_for_timeout(3000)
        check('在线失败时仍可开始诊断', 'PHY-' in page.locator('body').inner_text())

        page.screenshot(path=str(WORKDIR / 'data' / 'e2e-env' / 'settings-fallback.png'),
                        full_page=True)
        browser.close()
finally:
    stop_server()
    if had_env:
        ENV_FILE.write_bytes(BACKUP.read_bytes())
        BACKUP.unlink()
        print('      （已还原原有 .env）')
    elif ENV_FILE.exists():
        ENV_FILE.unlink()
        print('      （已删除临时 .env，仓库回到无密钥状态）')

check('.env 已还原为无密钥状态', not ENV_FILE.exists())

print()
if failures:
    print(f'== 在线配置回退验收未通过：{len(failures)} 项 ==')
    for name in failures:
        print('  -', name)
    sys.exit(1)
print('== 在线配置回退验收全部通过（配了在线但连不上：不崩、明确告知、回退 Mock）==')
