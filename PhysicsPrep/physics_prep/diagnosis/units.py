"""保守的单位检测。

设计取舍：只识别“明确写出的物理单位”，不做量纲推断。
- 下标 `_0` 等数字后缀不算作单位（epsilon_0 是常数名，不是“0”）。
- 单个字母（m、s、A、K、N、J、W、T、V、C、F、H）有歧义：可能只是符号名。
  因此只有在题目配置了 `expected_unit` 时才把单字母视为单位，否则忽略。
- 返回的只是提示信息，不参与判定，避免把物理量符号误判成单位错误。
"""
import re

# 多字母单位与明确带前缀的单位可以较安全地识别。
MULTI_LETTER_UNITS = frozenset('''
kg mol cd rad sr Hz Pa N J W C V F ohm S Wb T H lm lx Bq Gy Sv kat
min hour day deg atm bar eV
mm cm km nm um pm dm
ms us ns ps
kHz MHz GHz THz
mA kA mV kV MW kW GW mW nF uF pF nH uH mH
kPa MPa GPa hPa
mL uL nL
'''.split())

# 带负号/正号指数或多重后缀（m/s、m/s**2）中的基本单位。
BASE_UNITS = frozenset('m s g A K N J W C V F T H'.split())

MULTIPLIER_PREFIXES = (
    'da', 'Y', 'Z', 'E', 'P', 'T', 'G', 'M', 'k', 'h', 'd', 'c', 'm',
    'u', 'n', 'p', 'f', 'a', 'z', 'y',
)

TOKEN = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)')
TRAILING_UNIT = re.compile(r'(?<![\w.])([A-Za-z][A-Za-z0-9_]*)\s*$')
# 复合单位如 m/s、m/s**2、kg*m/s**2、N*m：整体识别，避免把 m 当成孤立符号名。
COMPOUND_UNIT = re.compile(
    r'(?<![\w.])([A-Za-z][A-Za-z0-9_]*(?:\s*(?:\*\*|/|\*|\^)\s*(?:-?\d+|[A-Za-z][A-Za-z0-9_]*))+)\b')
NUMBER_WITH_UNIT = re.compile(r'\d(?:[\d.]*)\s*([A-Za-z][A-Za-z0-9_]*)')


def _is_unit_word(word, allow_single_letter):
    if word in MULTI_LETTER_UNITS:
        return True
    if len(word) > 1:
        for prefix in MULTIPLIER_PREFIXES:
            rest = word[len(prefix):]
            if rest in MULTI_LETTER_UNITS or (allow_single_letter and rest in BASE_UNITS):
                return True
        return False
    return allow_single_letter and word in BASE_UNITS


def detect_units(text, expected_unit=None, allowed_symbols=None):
    """返回 (检测到的单位列表, 提示信息或 None)。

    只在“题目声明了单位要求”时给出提示，否则返回空结果（不打扰作答）。
    """
    if text is None:
        return [], None
    text = str(text)
    allowed = set(allowed_symbols or [])
    allow_single = bool(expected_unit)
    found = []
    for word in TOKEN.findall(text):
        if word in allowed or word in ('pi', 'E', 'I', 'e'):
            continue
        if '_' in word:
            continue
        if _is_unit_word(word, allow_single):
            found.append(word)
    # 复合单位（m/s、kg*m/s**2 等）即使题目未声明单位也能较安全地识别。
    for compound in COMPOUND_UNIT.findall(text):
        if any(part in allowed for part in TOKEN.findall(compound)):
            continue
        parts = [part for part in TOKEN.findall(compound)]
        if parts and all(_is_unit_word(part, True) for part in parts):
            found.append(compound.strip())
    found = list(dict.fromkeys(found))
    if not expected_unit:
        return found, None
    # 明确声明的单位：作答里出现单位但拼写不同 → 提示核对。
    numeric_with_unit = NUMBER_WITH_UNIT.search(text)
    trailing = TRAILING_UNIT.search(text.strip())
    candidate = None
    if numeric_with_unit and _is_unit_word(numeric_with_unit.group(1), True):
        candidate = numeric_with_unit.group(1)
    elif trailing and _is_unit_word(trailing.group(1), True):
        candidate = trailing.group(1)
    if candidate and candidate != expected_unit:
        return found, f'检测到单位「{candidate}」，但本题要求 {expected_unit}；请核对单位与量纲。'
    return found, None
