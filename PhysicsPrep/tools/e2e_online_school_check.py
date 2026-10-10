"""真实 GenAI 在线模式端到端验收（真实凭据 + 真实网络 + 真实模型）。

支持两种凭据来源：
1. 默认：DSH 本机凭据库里的 `DEEPSEEK_API_KEY` + 学校端点
   （baseURL `https://genaiapi.shanghaitech.edu.cn/api/v1/start`，模型 `deepseek-v4-pro`）；
2. `--env-file <path>`：直接借用另一个项目 `.env` 里已有的 `GENAI_*` 配置
   （例如 `fastgpt-physics-lab/env/.env` 使用的是 Paratera + `Kimi-K2.6`）。

在浏览器里验证：
1. 设置页报告为 GenAI 在线模式且不回显密钥；
2. 「测试模型连接」真的连通（不是回退 Mock）；
3. AI 教师作答前提问拿到**真实模型输出**（非 Mock 模板）。

安全：
- 密钥只写入临时 `.env`，脚本结束即删除（原本存在则还原）；
- **不打印**密钥，不写入任何报告文件；
- 只上传用户主动输入的问题文本，不上传教材/题库/学习记录。

用法：
    python tools/e2e_online_school_check.py [base_url] [server_workdir]
    python tools/e2e_online_school_check.py --env-file <other/.env>
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

CRED = Path.home() / '.dsh' / '.credentials.yaml'
DEFAULT_BASE = 'https://genaiapi.shanghaitech.edu.cn/api/v1/start'
DEFAULT_MODEL = 'deepseek-v4-pro'

# ---- 解析参数（保持位置参数向后兼容）----
ARGV = [a for a in sys.argv[1:]]
ENV_FILE_ARG = None
if '--env-file' in ARGV:
    idx = ARGV.index('--env-file')
    ENV_FILE_ARG = Path(ARGV[idx + 1])
    del ARGV[idx:idx + 2]
# --break-primary：故意把主模型改成一个不存在的 ID，用来**真实触发**降级链。
# 只替换主模型名，fallbacks 保持原样，因此可以验证“主模型坏 → 备用模型接手”。
BREAK_PRIMARY = '--break-primary' in ARGV
if BREAK_PRIMARY:
    ARGV.remove('--break-primary')
POSITIONAL = [a for a in ARGV if not a.startswith('--')]

BASE = POSITIONAL[0] if len(POSITIONAL) > 0 else 'http://127.0.0.1:7864'
WORKDIR = Path(POSITIONAL[1] if len(POSITIONAL) > 1 else '.').resolve()
PORT = int(BASE.rstrip('/').rsplit(':', 1)[-1])
ENV_FILE = WORKDIR / '.env'
BACKUP = WORKDIR / '.env.online-backup'

failures = []


def check(name, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + name + (f' :: {detail}' if detail else ''))
    if not ok:
        failures.append(name)


def read_env_file(path):
    values = {}
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        name, _, value = stripped.partition('=')
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_config():
    """返回 (key, base_url, model, fallbacks, 来源说明)。不打印密钥。"""
    if ENV_FILE_ARG:
        values = read_env_file(ENV_FILE_ARG)
        return (values.get('GENAI_API_KEY', ''),
                values.get('GENAI_BASE_URL', ''),
                values.get('GENAI_MODEL', ''),
                values.get('GENAI_MODEL_FALLBACKS', ''),
                f'{ENV_FILE_ARG} 中的 GENAI_* 配置')
    # 默认：项目自己的 .env（若存在），否则 DSH 凭据库 + 学校端点
    project_env = WORKDIR / '.env'
    if project_env.exists():
        values = read_env_file(project_env)
        if values.get('GENAI_API_KEY') and values.get('GENAI_BASE_URL'):
            return (values['GENAI_API_KEY'], values['GENAI_BASE_URL'],
                    values.get('GENAI_MODEL', ''),
                    values.get('GENAI_MODEL_FALLBACKS', ''),
                    f'{project_env} 中的 GENAI_* 配置')
    for line in CRED.read_text(encoding='utf-8').splitlines():
        if line.strip().startswith('DEEPSEEK_API_KEY:'):
            return (line.split(':', 1)[1].strip(), DEFAULT_BASE, DEFAULT_MODEL, '',
                    'DSH 本机凭据库 + 学校端点')
    return ('', '', '', '', '未找到任何凭据')


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
    env['PHYSICSPREP_DB_PATH'] = str(WORKDIR / 'data' / 'e2e-online' / 'study.sqlite3')
    env['PHYSICSPREP_OPEN_BROWSER'] = 'false'
    log = WORKDIR / 'data' / 'e2e-online' / 'server.log'
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


def main():
    print(f'== 真实 GenAI 在线验收  目标：{BASE} ==')
    key, base_url, model, fallbacks, source = resolve_config()
    if not (key and base_url and model):
        print(f'凭据不完整，跳过。来源：{source}')
        return 1
    print(f'凭据来源：{source}')
    print(f'凭据已获取（长度 {len(key)}，末四位 ****{key[-4:]}）')
    print(f'端点：{base_url}')
    fallback_list = [m.strip() for m in fallbacks.split(',') if m.strip()]
    if BREAK_PRIMARY:
        broken = model
        model = 'definitely-not-a-real-model-xyz'
        expected = fallback_list[0] if fallback_list else ''
        print(f'模型：{model}   ← 故意损坏（原本 {broken}），期望降级到 {expected or "无备用"}')
    else:
        print(f'模型：{model}')
    if fallback_list:
        print(f'降级链：{model} → ' + ' → '.join(fallback_list))
    host = base_url.split('//')[-1].split('/')[0]

    stop_server()
    had_env = ENV_FILE.exists()
    original_bytes = ENV_FILE.read_bytes() if had_env else None
    if had_env:
        BACKUP.write_bytes(original_bytes)

    try:
        ENV_FILE.write_text(
            f'GENAI_API_KEY={key}\n'
            f'GENAI_BASE_URL={base_url}\n'
            f'GENAI_MODEL={model}\n'
            f'GENAI_MODEL_FALLBACKS={",".join(fallback_list)}\n'
            'GENAI_TIMEOUT=60\n'
            'GENAI_MAX_RETRIES=2\n'
            'APP_MOCK_MODE=false\n',
            encoding='utf-8')
        check('已写入临时 .env（真实在线配置）', ENV_FILE.exists())

        check('服务以真实在线配置启动成功', start_server())

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.goto(BASE, wait_until='domcontentloaded')
            page.wait_for_selector('.stat-card', timeout=30000)

            page.get_by_role('tab', name=re.compile('设置与备份')).click()
            page.wait_for_timeout(2000)
            settings = page.locator('body').inner_text()
            check('设置页报告 GenAI 在线模式', 'GenAI 在线' in settings)
            check('设置页显示配置的端点主机', host in settings, host)
            check('设置页显示模型 ID', model in settings, model)
            check('设置页不回显密钥', key not in settings)
            if fallback_list:
                check('设置页显示降级顺序',
                      all(name in settings for name in fallback_list[:2]))

            print('   正在测试模型连接（真实网络调用）...')
            page.get_by_role('button', name=re.compile('测试模型连接')).click()
            # 真实模型延迟不稳定（首次冷启动可能超过 30s），必须轮询到结果真的出现，
            # 不能用固定 sleep 猜时间。
            result = ''
            for _ in range(60):
                page.wait_for_timeout(3000)
                result = page.locator('#connection-result').inner_text().strip()
                if '连接成功' in result or '已回退' in result or 'Mock 模式' in result:
                    break
            check('连接成功（真实在线模型）', '连接成功（在线模型）' in result,
                  result.replace('\n', ' ')[:120] or '<超时未返回结果>')
            check('未回退 Mock', '已回退 Mock' not in result)
            if BREAK_PRIMARY and expected:
                # 主模型是假的，所以“连接成功”只可能来自降级后的备用模型。
                # 这条断言才是降级逻辑真正生效的证据。
                check('主模型不可用时已降级到备用模型',
                      f'实际使用：`{expected}`' in result or expected in result,
                      result.replace('\n', ' ')[:160])
                check('报告了不可用的主模型', model in result)
            page.screenshot(path=str(WORKDIR / 'data' / 'e2e-online' / 'online-connection.png'),
                            full_page=True)

            # ---- AI 教师：作答前提问，必须是真实模型输出
            page.get_by_role('tab', name=re.compile('开始诊断')).click()
            page.wait_for_timeout(1500)
            page.locator('#start-btn').click()
            page.wait_for_timeout(3000)
            qid = page.evaluate("""() => {
                const m = document.body.innerText.match(/ID\\s+(PHY-[0-9A-Z\\-]+)/);
                return m ? m[1] : null; }""")
            check('已取到题目', qid is not None, str(qid))

            # AI 教师在折叠面板里，先展开再输入（用 elem_id 精确定位，
            # 避免 get_by_label 在 Gradio 生成的 wrapper 结构上匹配失败）
            page.get_by_role('button', name=re.compile('向 AI 教师提问')).click()
            page.wait_for_timeout(800)
            page.locator('#ai-prompt textarea').fill('这道题应该用哪个守恒定律？请只回答定律名称。')
            print('   正在向真实模型提问（作答前）...')
            page.locator('#ai-btn').click()
            page.wait_for_timeout(60000)
            answer = page.locator('#ai-response').inner_text()
            check('作答前提问已收到回答', len(answer.strip()) > 0, answer.replace('\n', ' ')[:100])
            check('回答不是 Mock 模板', '【Mock 教师，非模型推理】' not in answer)
            check('未发生在线回退', '已回退离线引导' not in answer)
            page.screenshot(path=str(WORKDIR / 'data' / 'e2e-online' / 'online-ai-answer.png'),
                            full_page=True)

            browser.close()

        # 服务日志里不应出现任何密钥
        log_text = (WORKDIR / 'data' / 'e2e-online' / 'server.log')
        if log_text.exists():
            content = log_text.read_text(encoding='utf-8', errors='ignore')
            check('服务日志未泄露密钥', key not in content)
    finally:
        stop_server()
        if had_env:
            ENV_FILE.write_bytes(BACKUP.read_bytes())
            BACKUP.unlink()
            print('      （已还原原有 .env）')
        elif ENV_FILE.exists():
            ENV_FILE.unlink()
            print('      （已删除临时 .env）')

    # 验收脚本必须把项目恢复原状：原本有 .env 就按原内容还原，
    # 原本没有就删掉自己写的临时文件。两种情况都不能残留测试配置。
    if had_env:
        check('.env 已按原内容还原', ENV_FILE.exists()
              and ENV_FILE.read_bytes() == original_bytes)
    else:
        check('.env 已删除（原本不存在）', not ENV_FILE.exists())

    print()
    if failures:
        print(f'== 真实在线验收未通过：{len(failures)} 项 ==')
        for name in failures:
            print('  -', name)
        return 1
    print(f'== 真实 GenAI 在线验收全部通过（{host} 实际连通）==')
    return 0


if __name__ == '__main__':
    sys.exit(main())
