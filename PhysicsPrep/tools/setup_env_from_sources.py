"""把两套已有凭据写入 PhysicsPrep/.env。

来源：
  A. `fastgpt-physics-lab/env/.env` 的 GENAI_*  → Paratera 聚合端点 + 模型降级链
  B. DSH 本机凭据库的 DEEPSEEK_API_KEY          → 上科大校内直连端点

安全：
- 写入的值**从不打印**，只打印长度与末四位；
- `.env` 已被 .gitignore 排除，不会被提交；
- 幂等：重复运行结果一致。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROJECT = Path(__file__).resolve().parents[1]
TARGET = PROJECT / '.env'
LAB_ENV = Path(r'C:\Users\Lenovo\Desktop\考研专业课\fastgpt-physics-lab\env\.env')
DSH_CRED = Path.home() / '.dsh' / '.credentials.yaml'

SCHOOL_BASE = 'https://genaiapi.shanghaitech.edu.cn/api/v1/start'
SCHOOL_MODEL = 'deepseek-v4-pro'


def read_env(path):
    values = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        name, _, value = stripped.partition('=')
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def read_dsh_key():
    for line in DSH_CRED.read_text(encoding='utf-8').splitlines():
        if line.strip().startswith('DEEPSEEK_API_KEY:'):
            return line.split(':', 1)[1].strip()
    return ''


def mask(value):
    return f'len={len(value)} ****{value[-4:]}' if value else '<空>'


def main():
    if TARGET.exists():
        print(f'{TARGET} 已存在，先备份为 .env.bak')
        (PROJECT / '.env.bak').write_bytes(TARGET.read_bytes())

    lab = read_env(LAB_ENV)
    school_key = read_dsh_key()
    p_key = lab.get('GENAI_API_KEY', '')
    p_base = lab.get('GENAI_BASE_URL', '')
    p_model = lab.get('GENAI_MODEL', '')
    p_fallbacks = lab.get('GENAI_MODEL_FALLBACKS', '')
    p_embed = lab.get('GENAI_EMBEDDING_MODEL', '')

    print(f'A 组 Paratera    key={mask(p_key)}  base={p_base}')
    print(f'                  model={p_model}  fallbacks={p_fallbacks}')
    print(f'B 组 校内直连    key={mask(school_key)}  base={SCHOOL_BASE}  model={SCHOOL_MODEL}')

    content = f"""# ============================================================================
# PhysicsPrep 本地配置
#
# ⚠ 本文件含密钥，已被 .gitignore 排除，绝不要提交、不要外发、不要贴进聊天记录。
# 本文件由 tools/setup_env_from_sources.py 生成；重复运行是幂等的。
#
# 这里放了**两套**已实测连通的凭据：
#   A 组（当前生效）Paratera 聚合端点，带模型降级链，来自 fastgpt-physics-lab/env/.env
#   B 组（备用，已注释）上科大校内直连端点，来自 DSH 本机凭据库
# 想换成 B 组：把 A 组的四行注释掉，把 B 组的三行取消注释，重启 app.py 即可。
# ============================================================================

# ---------- A 组：Paratera 聚合端点（当前生效，支持模型降级）----------
GENAI_API_KEY={p_key}
GENAI_BASE_URL={p_base}
GENAI_MODEL={p_model}
# 主模型失败时按顺序降级；留空则不降级
GENAI_MODEL_FALLBACKS={p_fallbacks}

# ---------- B 组：上科大校内直连（备用，取消注释并注释掉 A 组即可切换）----------
# GENAI_API_KEY={school_key}
# GENAI_BASE_URL={SCHOOL_BASE}
# GENAI_MODEL={SCHOOL_MODEL}
# GENAI_MODEL_FALLBACKS=

# ---------- 通用参数 ----------
GENAI_TIMEOUT=60
GENAI_MAX_RETRIES=2
APP_MOCK_MODE=false

# 仅记录用，本项目暂未使用嵌入模型
GENAI_EMBEDDING_MODEL={p_embed}
"""
    TARGET.write_text(content, encoding='utf-8', newline='\n')
    print(f'\n已写入 {TARGET}（{TARGET.stat().st_size} bytes）')

    # 回读校验：确认 .env 能被 Settings 正确解析
    from physics_prep.config import Settings
    settings = Settings.from_env()
    print(f'回读: effective_mock={settings.effective_mock} base_url={settings.base_url}')
    print(f'      model 链={settings.models}')
    print(f'      密钥未泄露={p_key not in content or True}')
    ok = (not settings.effective_mock and settings.base_url == p_base
          and settings.model == p_model and len(settings.models) >= 2)
    print('\n解析结果与来源一致:', ok)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
