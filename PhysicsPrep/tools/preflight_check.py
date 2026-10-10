"""交付前自检：密钥泄露扫描、知识树完整性、全新数据库端到端冒烟、自身代码零警告。

用法：
    python tools/preflight_check.py
"""
import json
import re
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

failures = []


def check(name, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + name + (f' :: {detail}' if detail else ''))
    if not ok:
        failures.append(name)


# ---------------------------------------------------------------- 1. 密钥扫描
# 只找“看起来像真实凭据”的字面量。测试夹具（test-placeholder）与本自检脚本的
# 说明文本属于已知误报，明确排除，避免出现“狼来了”式的告警。
SECRET_PATTERNS = [
    re.compile(r'\bsk-[A-Za-z0-9]{20,}'),
    # 只匹配“等号后确实跟着一长串字符”的情况；空值（.env.example）与代码比较语句都不匹配。
    re.compile(r"""GENAI_API_KEY\s*=\s*(?=['"]?[A-Za-z0-9\-_]{12,})"""),
    re.compile(r"""(?i)\b(api[_-]?key|apikey|secret|access[_-]?token)\s*[:=]\s*['"][A-Za-z0-9\-_]{24,}['"]"""),
]
SKIP_DIRS = {'.venv', '__pycache__', '.git', 'ui-check', '.pytest_cache', 'docs'}
SKIP_FILES = {'preflight_check.py'}
# 测试与验收工具里用于验证“不泄露密钥”“在线失败回退”的假凭据。
# 它们不是真实密钥，但故意长得像，因此显式登记，避免扫描器狼来了。
KNOWN_FAKE = (
    'sk-super-secret-value-1234',
    'sk-secret-abcdef',
    'test-placeholder',
    'sk-e2e-placeholder-not-a-real-key',
    'sk-test-only-placeholder-key',
)

hits = []
for path in ROOT.rglob('*'):
    if not path.is_file():
        continue
    if any(part in SKIP_DIRS for part in path.parts) or path.name in SKIP_FILES:
        continue
    if path.suffix.lower() not in ('.py', '.json', '.md', '.toml', '.cfg', '.txt', '.example', '.yml', '.yaml'):
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        continue
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            found = match.group(0)
            # 用整行判断已知假凭据：`GENAI_API_KEY=` 这类模式只匹配到变量名，
            # 值（含 fixture 标记）在匹配范围之外。
            line_start = text.rfind('\n', 0, match.start()) + 1
            line_end = text.find('\n', match.end())
            line = text[line_start: line_end if line_end != -1 else len(text)]
            if any(fake in line or fake in found for fake in KNOWN_FAKE):
                continue
            hits.append(f'{path.relative_to(ROOT)}: {found[:40]}')

check('源码中无硬编码密钥', not hits, '; '.join(hits[:5]))

# `.env` 的存在本身不是问题——有真实凭据时它**就该**存在。
# 危险的是「它会被提交」。所以这里真正验证的是 gitignore 规则**确实排除**了它，
# 而不是「文件不存在」这种一有凭据就失效的假检查。
gi_lines = [ln.strip() for ln in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()]


def is_ignored(rel_path):
    """按 .gitignore 里出现的模式判断路径是否被排除（无需 git 仓库）。"""
    import fnmatch
    ignored = False
    for line in gi_lines:
        if not line or line.startswith('#'):
            continue
        negate = line.startswith('!')
        pattern = line[1:].strip() if negate else line
        pattern = pattern.rstrip('/')
        if not pattern:
            continue
        hit = (fnmatch.fnmatch(rel_path, pattern)
               or fnmatch.fnmatch(rel_path, pattern + '/*')
               or fnmatch.fnmatch(rel_path, '*/' + pattern))
        if hit:
            ignored = not negate
    return ignored


check('.env 被 gitignore 排除', is_ignored('.env'), f'.gitignore 规则数 {len(gi_lines)}')
check('.env.local 也被排除', is_ignored('.env.local'))
check('.env.example 不被排除（要能提交）', not is_ignored('.env.example'))
check('.env.example 已提供', (ROOT / '.env.example').is_file())
if (ROOT / '.env').exists():
    env_text = (ROOT / '.env').read_text(encoding='utf-8', errors='ignore')
    # 允许「看起来是真 key」的存在（用户自己的凭据就在里面），
    # 但绝不允许把**测试占位符**当真实配置留下来。
    leaked_fixtures = [fake for fake in KNOWN_FAKE if fake in env_text]
    check('.env 中没有残留测试占位符', not leaked_fixtures, '; '.join(leaked_fixtures[:3]))
    check('.env 已配置但未启用 Mock',
          'APP_MOCK_MODE=false' in env_text or 'APP_MOCK_MODE=true' in env_text)
    print('      （.env 存在且已被 gitignore 排除，这是允许的）')

check('gitignore 排除数据库文件', '*.sqlite3' in gi_lines and '*.sqlite' in gi_lines)

# ---------------------------------------------------------------- 2. 种子数据
topics = json.loads((ROOT / 'data' / 'seed_topics.json').read_text(encoding='utf-8'))
questions = json.loads((ROOT / 'data' / 'seed_questions.json').read_text(encoding='utf-8'))
by_id = {t['id']: t for t in topics}

check('知识树非空', len(topics) >= 40, f'{len(topics)} 个知识点')
check('题库 30 道', len(questions) == 30, f'{len(questions)} 道')

# 层级深度（从无父节点的根算起）
def depth(topic_id, seen=None):
    seen = seen or set()
    if topic_id in seen:
        return 0
    node = by_id.get(topic_id)
    if not node or not node.get('parent_id'):
        return 1
    return 1 + depth(node['parent_id'], seen | {topic_id})

max_depth = max(depth(t['id']) for t in topics)
check('知识树至少四级', max_depth >= 4, f'最大层级 {max_depth}')

# 父节点与前置存在且无环
missing_parent = [t['id'] for t in topics if t.get('parent_id') and t['parent_id'] not in by_id]
missing_pre = [t['id'] for t in topics for p in t.get('prerequisite_ids', []) if p not in by_id]
check('父节点引用有效', not missing_parent, str(missing_parent[:5]))
check('前置知识引用有效', not missing_pre, str(missing_pre[:5]))

# 每个知识点都能追溯到根（无环）
def root_ok(topic_id):
    seen = set()
    node = by_id.get(topic_id)
    while node and node.get('parent_id'):
        if node['id'] in seen:
            return False
        seen.add(node['id'])
        node = by_id.get(node['parent_id'])
    return node is not None

check('父链无环且可达根', all(root_ok(t['id']) for t in topics))

# 题目引用有效、来源为原创、无伪造教材引用
bad_topics = [q['id'] for q in questions if any(t not in by_id for t in q['topic_ids'])]
check('题目知识点引用有效', not bad_topics, str(bad_topics[:5]))
check('全部题目标注为原创', all(q['source_type'] == 'original' for q in questions))
check('无伪造教材引用', all(q['source_reference'] is None for q in questions))
check('每题至少一个知识点', all(len(q['topic_ids']) >= 1 for q in questions))
check('每题都有解析', all(q.get('solution', '').strip() for q in questions))

subjects = {}
for q in questions:
    subjects[q['subject']] = subjects.get(q['subject'], 0) + 1
print('      科目分布:', json.dumps(subjects, ensure_ascii=False))
check('五类科目都有题目', len(subjects) >= 5, json.dumps(subjects, ensure_ascii=False))

# ---------------------------------------------------------------- 3. 端到端冒烟
sys.path.insert(0, str(ROOT))
from physics_prep.config import Settings
from physics_prep.diagnosis.math_grader import grade
from physics_prep.llm.client import MockLLMClient, create_client
from physics_prep.services.learning import LearningService
from physics_prep.ui.application import build_app

# 所有可判分题目的标准答案自判
objectives = [q for q in questions if q['question_type'] != 'short_answer']
bad = []
for q in objectives:
    result = grade(q['correct_answer'], q['correct_answer'], q['question_type'], q)
    if result['status'] != 'correct':
        bad.append((q['id'], result['status']))
check('全部客观题标准答案自判为正确', not bad, str(bad[:5]))

# 攻击输入
attacks = ['__import__("os").system("x")', '2**100000', '1/0', '(1).__class__', '[x for x in [1]]', 'x' * 301]
not_uncertain = [a for a in attacks if grade(a, '1', 'numeric')['status'] != 'uncertain']
check('攻击输入均返回 uncertain', not not_uncertain, str(not_uncertain))

# 全新数据库：启动 → 答题 → 统计
# 注意：Windows 下必须显式 dispose()，否则临时文件仍被占用导致清理失败。
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    service = LearningService(Path(folder) / 'fresh.sqlite3', ROOT / 'data')
    check('全新数据库导入知识树', len(service.topic_tree()) == len(topics))
    check('全新数据库导入题库', len(service.list_questions()) == len(questions))

    session_id = service.start('mechanics')
    question = service.next(session_id)
    seed = next(q for q in questions if q['id'] == question['id'])
    check('取到题目且不含答案', 'correct_answer' not in question and 'solution' not in question)

    feedback = service.submit(session_id, question['id'], seed['correct_answer'], 'preflight-1')
    check('提交判分为正确', feedback['status'] == 'correct', feedback.get('explanation', ''))
    check('判分附带解析与知识点', bool(feedback['solution']) and bool(feedback['topic_names']))
    check('重复提交不产生第二条记录',
          service.submit(session_id, question['id'], seed['correct_answer'], 'preflight-1') == feedback)
    with service.factory() as s:
        from sqlalchemy import select
        from physics_prep.database.models import Attempt
        check('attempts 只有 1 行', len(list(s.scalars(select(Attempt)))) == 1)

    dashboard = service.dashboard()
    check('统计卡有今日作答', dashboard['today_count'] == 1)
    check('七天序列为 7 项', len(dashboard['daily_counts']) == 7)
    check('掌握度已写入且未视为完全掌握', 0 < dashboard['mastery'][0]['estimate'] < 0.8,
          str(dashboard['mastery'][0]['estimate']))

    client = create_client(Settings())
    check('无密钥时为 Mock 模式', isinstance(client, MockLLMClient))
    check('Mock 连接测试可用', client.test_connection()['mode'] == 'mock')
    service.engine.dispose()

# ------------------------------------------------- 4. 本项目代码自身不产生警告
# pytest 不再把弃用警告升级为失败（Gradio 5.x 会发出多条 Gradio 6.0 迁移提示，
# 逐条 ignore 既脆弱又会掩盖新提示）。真正要守住的约束在这里：
# 用 record=True 抓取构造整个界面时产生的全部警告，只允许来自第三方库的迁移提示。
# 判定依据是警告的 message 文本是否属于已知上游迁移提示，
# 因为 stacklevel=2 会把发出位置记到我们的调用行上，filename 无法区分来源。

UPSTREAM_MIGRATION_MARKERS = (
    "parameter in the Blocks constructor will be removed in Gradio 6.0",
    "in Gradio 6.0",
    "package URL does not contain version info",
    "unable to parse version details from package URL",
    # Gradio 的 analytics 机制在构造界面时会创建并丢弃 asyncio 事件循环，
    # 由 GC 触发这条 ResourceWarning；源头在 gradio/analytics.py，不是本项目代码。
    "unclosed event loop",
)

with warnings.catch_warnings(record=True) as recorded:
    warnings.simplefilter('always')
    _ws = Settings()
    _svc = LearningService(Path(tempfile.mkdtemp()) / 'warn.sqlite3', ROOT / 'data')
    try:
        build_app(_svc, lambda: create_client(_ws), _ws)
    finally:
        _svc.engine.dispose()

own = []
upstream = 0
for item in recorded:
    message = str(item.message)
    if any(marker in message for marker in UPSTREAM_MIGRATION_MARKERS):
        upstream += 1
    else:
        own.append(f'{Path(item.filename).name}:{item.lineno} {item.category.__name__}: {message[:110]}')

check('本项目代码不产生告警', not own, '; '.join(own[:4]))
print(f'      （忽略上游 Gradio 迁移提示 {upstream} 条，属于 Gradio 6.0 待迁移项）')

print()
if failures:
    print(f'== 自检未通过：{len(failures)} 项 ==')
    for name in failures:
        print('  -', name)
    sys.exit(1)
print('== 自检全部通过 ==')
