"""读取指定 .env 中 GENAI_* 的**结构**（端点/模型可见，密钥只报长度与末四位）。"""
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else
            r'C:\Users\Lenovo\Desktop\考研专业课\fastgpt-physics-lab\env\.env')

SHOW_PLAIN = {'GENAI_BASE_URL', 'GENAI_MODEL', 'GENAI_MODEL_FALLBACKS',
              'GENAI_EMBEDDING_MODEL', 'GENAI_TIMEOUT', 'GENAI_MAX_RETRIES',
              'APP_MOCK_MODE'}
WANT = SHOW_PLAIN | {'GENAI_API_KEY'}

print(f'文件: {path}  ({path.stat().st_size} bytes)\n')
for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith('#') or '=' not in stripped:
        continue
    name, _, value = stripped.partition('=')
    name = name.strip()
    if name not in WANT:
        continue
    value = value.strip().strip('"').strip("'")
    if name in SHOW_PLAIN:
        print(f'{name:26s} = {value}')
    else:
        print(f'{name:26s} = len={len(value)} ****{value[-4:]}')
