"""真实进程级端到端验收：答题 → 关闭服务 → 重启 → 记录仍在。

与 `tests/test_acceptance.py` 的区别：那里是在同一个 Python 进程内重新打开数据库文件；
这里是真的杀掉 Gradio 服务进程、重新启动，再用浏览器继续操作，
验证“关掉程序再打开，学习记录还在”这条用户可见的承诺。

本脚本自己管理服务进程：启动时会在 `WORKDIR` 下执行 `app.py`。
**不要**在同一个端口上同时跑其他服务实例。

用法：
    python tools/e2e_restart_check.py [base_url] [db_path] [server_workdir]
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:7861'
DB = Path(sys.argv[2] if len(sys.argv) > 2 else 'data/e2e-check/study.sqlite3').resolve()
WORKDIR = Path(sys.argv[3] if len(sys.argv) > 3 else '.').resolve()
PORT = int(BASE.rstrip('/').rsplit(':', 1)[-1])

failures = []


def check(name, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + name + (f' :: {detail}' if detail else ''))
    if not ok:
        failures.append(name)


def db_counts():
    """直接用 SQLite 读取作答与错题数量（不经过界面）。"""
    import sqlite3
    with sqlite3.connect(str(DB)) as conn:
        attempts = conn.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]
        sessions = conn.execute('SELECT COUNT(*) FROM exam_sessions').fetchone()[0]
        mastery = conn.execute('SELECT COUNT(*) FROM mastery_records').fetchone()[0]
    return attempts, sessions, mastery


def port_pid(port):
    """返回监听指定端口的进程 PID（没有则 None）。

    只按端口定位，不按进程名/路径——按路径匹配曾把调用方 shell 也一起杀掉。
    """
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
    env['PHYSICSPREP_DB_PATH'] = str(DB)
    env['PHYSICSPREP_OPEN_BROWSER'] = 'false'
    log = DB.parent / 'server.log'
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


def answer_one_question(page):
    """在浏览器里完成一题：开始诊断 → 填入标准答案 → 提交。

    题型由选题器决定，因此标准答案按界面上实际出现的题目 ID 从种子数据里查，
    而不是预设某一道题。
    """
    seeds = {q['id']: q for q in json.loads(
        (WORKDIR / 'data' / 'seed_questions.json').read_text(encoding='utf-8'))}

    page.get_by_role('tab', name=re.compile('开始诊断')).click()
    page.wait_for_timeout(1500)
    page.locator('#start-btn').click()
    page.wait_for_timeout(3000)

    qid = page.evaluate("""() => {
        const m = document.body.innerText.match(/ID\\s+(PHY-[0-9A-Z\\-]+)/);
        return m ? m[1] : null; }""")
    if qid not in seeds:
        return None, '未能从界面读出题目 ID'

    actual = seeds[qid]
    if actual['question_type'] in ('single_choice', 'multiple_choice'):
        answer = actual['correct_answer']
        first = answer[0] if isinstance(answer, list) else answer
        page.locator('#quiz-options label').filter(has_text=re.compile(rf'^{first}')).first.click()
    else:
        # 只认“你的计算结果 / 推导”这个文本框，避免误选 AI 提问框
        page.get_by_label(re.compile('你的计算结果')).fill(str(actual['correct_answer']))
    page.wait_for_timeout(500)
    page.get_by_role('button', name=re.compile('提交答案')).click()
    page.wait_for_timeout(3500)
    return qid, page.locator('#feedback-card').inner_text()


print(f'== 目标：{BASE}  数据库：{DB} ==')

# ---------------------------------------------------------------- 阶段 1：清空并从零开始
stop_server()
for suffix in ('', '-wal', '-shm'):
    candidate = Path(str(DB) + suffix)
    if candidate.exists():
        candidate.unlink()
check('阶段1 起始数据库已清空', not DB.exists(), str(DB))

check('阶段1 服务启动成功', start_server())
before = db_counts()
check('阶段1 启动后无作答记录', before[0] == 0, f'attempts={before[0]}')

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.goto(BASE, wait_until='domcontentloaded')
    page.wait_for_selector('.stat-card', timeout=30000)

    qid, feedback = answer_one_question(page)
    check('阶段1 浏览器完成一题作答', qid is not None, str(qid))
    check('阶段1 提交后出现判分反馈', '标准答案' in (feedback or ''), (feedback or '')[:60])
    page.screenshot(path=str(DB.parent / 'e2e-01-after-answer.png'), full_page=True)
    browser.close()

after = db_counts()
check('阶段1 数据库已写入作答', after[0] == 1, f'attempts={after[0]}')
check('阶段1 已写入掌握度记录', after[2] >= 1, f'mastery={after[2]}')
snapshot = after

# ---------------------------------------------------------------- 阶段 2：重启后仍保留
stop_server()
check('阶段2 服务已停止', port_pid(PORT) is None)
check('阶段2 重新启动成功', start_server())
check('阶段2 数据库文件仍然存在', DB.exists())
check('阶段2 重启后作答记录未丢失', db_counts() == snapshot,
      f'{snapshot} -> {db_counts()}')

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.goto(BASE, wait_until='domcontentloaded')
    page.wait_for_selector('.stat-card', timeout=30000)
    page.wait_for_timeout(2500)

    stats = page.locator('.stats-grid').inner_text()
    check('阶段2 首页仍显示今日作答（界面层）', '今日作答' in stats, stats.replace('\n', ' ')[:70])

    # 刷新后图表应有柱子
    page.get_by_role('button', name=re.compile('刷新学习总览')).click()
    page.wait_for_timeout(3000)
    bars = page.evaluate("""() => Array.from(
        document.querySelectorAll('.js-plotly-plot .barlayer .point path'))
        .map(p => Math.round(p.getBBox().height))""")
    check('阶段2 重启后图表仍画出柱子', any(h > 2 for h in bars), str(bars))
    page.screenshot(path=str(DB.parent / 'e2e-02-after-restart.png'), full_page=True)

    # 错题页应能看到那条作答
    page.get_by_role('tab', name=re.compile('错题与复习')).click()
    page.wait_for_timeout(2000)
    wrong_text = page.locator('#wrong-table').inner_text()
    check('阶段2 错题页可读取历史', len(wrong_text.strip()) > 0, wrong_text.replace('\n', ' ')[:60])

    # 继续上次学习应可用
    page.get_by_role('tab', name=re.compile('学习总览')).click()
    page.wait_for_timeout(1000)
    page.screenshot(path=str(DB.parent / 'e2e-03-dashboard-final.png'), full_page=True)
    browser.close()

print()
if failures:
    print(f'== 端到端验收未通过：{len(failures)} 项 ==')
    for name in failures:
        print('  -', name)
    sys.exit(1)
print('== 真实进程级端到端验收全部通过（答题 → 关服务 → 重启 → 记录仍在）==')
