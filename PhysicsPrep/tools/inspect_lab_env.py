"""列出 `fastgpt-physics-lab/env/.env` 中的变量名与"是否已填值"。

只输出变量名、值的长度与末四位，**从不打印完整值**，用于判断有哪些可用凭据。
"""
import re
import sys
from pathlib import Path

env_path = Path(sys.argv[1] if len(sys.argv) > 1 else
                r'C:\Users\Lenovo\Desktop\考研专业课\fastgpt-physics-lab\env\.env')

if not env_path.exists():
    print(f'找不到 {env_path}')
    sys.exit(1)

print(f'文件: {env_path}  ({env_path.stat().st_size} bytes)\n')

filled, empty = [], []
for line in env_path.read_text(encoding='utf-8', errors='replace').splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        continue
    match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', stripped)
    if not match:
        continue
    name, value = match.group(1), match.group(2).strip().strip('"').strip("'")
    if value:
        filled.append((name, len(value), value[-4:]))
    else:
        empty.append(name)

print(f'=== 已填值 ({len(filled)}) ===')
for name, length, tail in sorted(filled):
    print(f'  {name:42s} len={length:<4} ****{tail}')
print(f'\n=== 空值 ({len(empty)}) ===')
for name in sorted(empty):
    print(f'  {name}')
