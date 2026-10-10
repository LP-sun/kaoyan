"""逐个探测候选模型是否可用（真实网络）。

用于确认 `GENAI_MODEL` 与 `GENAI_MODEL_FALLBACKS` 里的模型是否真的能调通。
只打印状态码与简短响应，不打印密钥。

用法：
    python tools/probe_models_available.py <base_url> <key> <model> [model...]
或：
    python tools/probe_models_available.py --from-env-file <path>
"""
import sys
import time
from pathlib import Path

import httpx


def read_env(path):
    values = {}
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        name, _, value = stripped.partition('=')
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == '--from-env-file':
        cfg = read_env(args[1])
        base = cfg.get('GENAI_BASE_URL', '')
        key = cfg.get('GENAI_API_KEY', '')
        models = [cfg.get('GENAI_MODEL', '')]
        models += [m.strip() for m in cfg.get('GENAI_MODEL_FALLBACKS', '').split(',') if m.strip()]
    else:
        if len(args) < 3:
            print(__doc__)
            return 1
        base, key, models = args[0], args[1], args[2:]

    print(f'端点: {base}')
    print(f'密钥: len={len(key)} ****{key[-4:]}\n')
    url = base.rstrip('/') + '/chat/completions'
    for model in models:
        started = time.time()
        try:
            response = httpx.post(
                url,
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json={'model': model,
                      'messages': [{'role': 'user', 'content': '只回复两个字：可用'}],
                      'max_tokens': 32},
                timeout=90.0)
            detail = ''
            if response.status_code == 200:
                body = response.json()
                content = (body.get('choices') or [{}])[0].get('message', {}).get('content', '')
                detail = f"served_as={body.get('model')} 回答={content.strip()[:40]!r}"
            else:
                detail = response.text[:140].replace('\n', ' ')
            print(f'{model:24s} HTTP {response.status_code}  {time.time() - started:5.1f}s  {detail}')
        except Exception as exc:
            print(f'{model:24s} {type(exc).__name__}  {time.time() - started:5.1f}s')
        time.sleep(1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
