"""探测学校 GenAI 端点的可用路径与模型。

背景：DSH 的 `llm-deepseek` 配置里 baseURL 是
`https://genaiapi.shanghaitech.edu.cn/api/v1/start`，
该地址 `/models` 返回 200 但模型列表为空，需要确认正确的调用路径与模型 ID。

安全约定：**不打印密钥**；只打印状态码、路径与响应结构（截断）。
"""
import json
import sys
from pathlib import Path

import httpx

CRED = Path.home() / '.dsh' / '.credentials.yaml'
HOST = 'https://genaiapi.shanghaitech.edu.cn'


def load_key(name='DEEPSEEK_API_KEY'):
    for line in CRED.read_text(encoding='utf-8').splitlines():
        if line.strip().startswith(name + ':'):
            return line.split(':', 1)[1].strip()
    return None


def main():
    key = load_key()
    print(f'key: {"已获取 len=%d" % len(key) if key else "不可用"}')
    headers = {'Authorization': f'Bearer {key}'}

    candidates = [
        '/api/v1/start',
        '/api/v1/start/models',
        '/api/v1/models',
        '/v1/models',
        '/api/v1/start/chat/completions',
        '/api/v1/chat/completions',
        '/v1/chat/completions',
    ]
    for path in candidates:
        try:
            if path.endswith('/models'):
                r = httpx.get(HOST + path, headers=headers, timeout=20.0)
            else:
                r = httpx.post(HOST + path, headers={**headers, 'Content-Type': 'application/json'},
                               json={'model': 'deepseek-v4-pro',
                                     'messages': [{'role': 'user', 'content': 'hi'}],
                                     'max_tokens': 16},
                               timeout=25.0)
            body = r.text[:220].replace(key, '<redacted>') if key else r.text[:220]
            print(f'POST/GET {path:38s} -> {r.status_code}  {body}')
        except Exception as exc:
            print(f'{path:38s} -> {type(exc).__name__}: {str(exc)[:100]}')

    print('\n--- 直接用 chat/completions 试几个模型 ID ---')
    for model in ('deepseek-v4-pro', 'DeepSeek-V4-Pro', 'deepseek-chat', 'DeepSeek-V3.2'):
        for path in ('/api/v1/start/chat/completions', '/v1/chat/completions'):
            try:
                r = httpx.post(HOST + path,
                               headers={**headers, 'Content-Type': 'application/json'},
                               json={'model': model,
                                     'messages': [{'role': 'user', 'content': '只回复：可用'}],
                                     'max_tokens': 24},
                               timeout=40.0)
                body = r.text[:200].replace(key, '<redacted>') if key else r.text[:200]
                print(f'{model:20s} {path:34s} -> {r.status_code}  {body}')
                if r.status_code == 200:
                    break
            except Exception as exc:
                print(f'{model:20s} {path:34s} -> {type(exc).__name__}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
