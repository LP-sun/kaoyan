"""大纲细目 × 题源覆盖看板。

只做一件事：把逐题相关性初筛得到的主题，与另外三个题源（基础题、PhysicsPrep
种子题、fastgpt-lab 题）对到同一套大纲细目上，算出每个细目在各口径下有多少题，
把缺口暴露出来。

口径必须分清，否则数字会被误读：
- 「候选」是关键词自动初筛命中，**不是人工核验**。核验数单独成列，当前全为 0。
- 候选数包含待复核的误命中，也包含超出本细目考查深度的题，不能当"可做题量"。
- 一道题可命中多个主题，故各主题候选数之和 **大于** 题目总数，不可相加。

本脚本不修改任何题库数据，只输出看板 JSON 与 Markdown。
"""
import json
from pathlib import Path
from collections import defaultdict

R = Path(__file__).resolve().parent
T = R / '题库'
W = R.parent / 'PhysicsPrep'
L = R.parent / 'fastgpt-physics-lab'

relevance = json.loads((T / '考研相关性.json').read_text(encoding='utf-8'))
rules, rows = relevance['rules'], relevance['questions']

# 相关性初筛的主题名 -> 大纲教材对应表使用的细目名（个别措辞不同，不改题库数据）
TOPIC_ALIAS = {
    '热力学': '热力学与熵',
    '直流与交流电路': '交直流电路',
    '电磁学国际单位制': '国际单位制',
    '光的衍射与分光性能': '光的衍射与仪器',
}

# 细目 -> 它属于哪门考试。由 rules 反推，一个细目可同时属于两科。
exams_of = defaultdict(set)
for r in rules:
    exams_of[TOPIC_ALIAS.get(r['topic'], r['topic'])].add(r['exam'])

# 每个细目的考查要求与大纲页码（同一名在多科出现时合并标注）
detail = {}
for r in rules:
    name = TOPIC_ALIAS.get(r['topic'], r['topic'])
    d = detail.setdefault(name, {
        'topic': name,
        'exams': sorted(exams_of[name]),
        'requirement': r['level'],
        'syllabus_page': r['syllabus_page'],
        'syllabus_pdf': '普物大纲.pdf' if r['exam'] == '651' else '量子大纲.pdf',
        'books': sorted(set(r['books'].split())),
    })
    if r['level'] != d['requirement']:
        d['requirement'] = f"{d['requirement']}/{r['level']}"

# 1) 教材题库：按主题统计分层，并单独统计已人工核验数
textbook = defaultdict(lambda: defaultdict(int))
verified = defaultdict(int)
for q in rows:
    if q['review_status'] != '自动初筛，未逐题原页复核':
        for e in q['exams']:
            for h in q['exams'][e]['evidence']:
                verified[TOPIC_ALIAS.get(h['topic'], h['topic'])] += 1
    for e, a in q['exams'].items():
        for h in a['evidence']:
            textbook[TOPIC_ALIAS.get(h['topic'], h['topic'])][f"{e}_{a['tier']}"] += 1

# 2) 基础题（原创，含答案与易错点）
basic = json.loads((T / '基础题库.json').read_text(encoding='utf-8'))
basic_by = defaultdict(int)
for q in basic:
    basic_by[TOPIC_ALIAS.get(q['topic'], q['topic'])] += 1

# 3) PhysicsPrep 种子题：subject+topic_ids 需经其知识树映射到中文细目名
prep_by = defaultdict(int)
prep_unmatched = []
if (W / 'data' / 'seed_questions.json').exists():
    seed_q = json.loads((W / 'data' / 'seed_questions.json').read_text(encoding='utf-8'))
    seed_t = json.loads((W / 'data' / 'seed_topics.json').read_text(encoding='utf-8'))
    tname = {t['id']: t['name'] for t in seed_t}
    for q in seed_q:
        names = {tname.get(t, t) for t in q.get('topic_ids', [])}
        hit = [n for n in names if n in detail]
        if hit:
            for n in set(hit):
                prep_by[n] += 1
        else:
            prep_unmatched.append({'id': q['id'], 'names': sorted(names)})

# 4) fastgpt-lab 题库：用 chapter 字段匹配细目名
lab_by = defaultdict(int)
lab_unmatched = []
if (L / 'bank' / 'questions.json').exists():
    lab = json.loads((L / 'bank' / 'questions.json').read_text(encoding='utf-8'))
    items = lab if isinstance(lab, list) else lab.get('questions', [])
    for q in items:
        ch = (q.get('chapter') or q.get('topic') or '')
        hit = [n for n in detail if n in ch or ch in n]
        if hit:
            lab_by[hit[0]] += 1
        else:
            lab_unmatched.append({'id': q.get('id'), 'chapter': ch})

# 汇总
ORDER = ['651', '803']
board = []
for name, meta in detail.items():
    tb = textbook.get(name, {})
    row = dict(meta)
    row.update({
        'bk_candidate': tb.get('651_大纲候选', 0) + tb.get('803_大纲候选', 0),
        'bk_concept': tb.get('651_概念了解', 0) + tb.get('803_概念了解', 0),
        'bk_651_candidate': tb.get('651_大纲候选', 0),
        'bk_651_concept': tb.get('651_概念了解', 0),
        'bk_803_candidate': tb.get('803_大纲候选', 0),
        'bk_803_concept': tb.get('803_概念了解', 0),
        'bk_verified': verified.get(name, 0),
        'basic': basic_by.get(name, 0),
        'prep_seed': prep_by.get(name, 0),
        'lab_bank': lab_by.get(name, 0),
    })
    # 可直接闭卷练习 = 有答案的原创题，不含仅有教材题面的候选
    row['answerable'] = row['basic'] + row['prep_seed'] + row['lab_bank']
    board.append(row)

for exam in ORDER:
    for r in board:
        if exam in r['exams']:
            r['_sort'] = (ORDER.index(exam), r['syllabus_page'], r['topic'])
board.sort(key=lambda r: r.pop('_sort'))

(T / '大纲覆盖看板.json').write_text(
    json.dumps({'generated_from': relevance['method'],
                'note': '候选为自动初筛命中，未经人工核验；一题可命中多主题，列不可相加',
                'details': board}, ensure_ascii=False, indent=2), encoding='utf-8')

# Markdown 看板
def exam_tag(e): return '+'.join(e)
md = ['# 大纲覆盖缺口看板',
      '',
      '由 `大纲覆盖看板.py` 生成，数据源见文末。**请勿手改本文件。**',
      '',
      '## 怎么读这些列',
      '',
      '- **教材候选**：相关性初筛命中的题面记录数。这是**自动关键词匹配**，不是人工核验，'
      '含误命中，也含考查深度超范围的题，**不等于可做题量**。',
      '- **已核验**：经过原页人工复核的教材题。**这是真正决定进度的列。**',
      '- **有答案**：已写出可闭卷核对的解答的题（基础题 + PhysicsPrep 种子 + lab 题库），'
      '三者都是原创题，不含教材原题。',
      '- 一题可命中多个主题，故各行的「教材候选」相加会大于 2,007，**不能纵向求和**。',
      '']

for exam in ORDER:
    sub = [r for r in board if exam in r['exams']]
    tot_c = sum(r[f'bk_{exam}_candidate'] + r[f'bk_{exam}_concept'] for r in sub)
    zero_a = [r for r in sub if r['answerable'] == 0]
    zero_v = [r for r in sub if r['bk_verified'] == 0]
    md += [f'## {exam}', '',
           f'- 细目数：{len(sub)}；教材题面命中合计 {tot_c} 条（含跨主题重复计入）',
           f'- 人工已核验：{len(sub) - len(zero_v)} / {len(sub)} 个细目',
           f'- **零可做题（无任何带答案题）：{len(zero_a)} / {len(sub)} 个细目**',
           '',
           '| 大纲页 | 细目 | 要求 | 教材候选 | 其中概念题 | 已核验 | 基础题 | Prep种子 | lab题 | 缺口 |',
           '| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for r in sub:
        c = r[f'bk_{exam}_candidate']
        if r['answerable'] == 0 and c == 0:
            gap = '🔴 完全无题源'
        elif r['answerable'] == 0:
            gap = '🟠 有题面，无答案'
        elif r['bk_verified'] == 0 and r['answerable'] < 2:
            gap = '🟡 仅个别题且未核验'
        else:
            gap = '🟢 有可做题'
        md.append(f"| {r['syllabus_page']} | {r['topic']} | {r['requirement']} | {c} "
                  f"| {r[f'bk_{exam}_concept']} | {r['bk_verified']} | {r['basic']} "
                  f"| {r['prep_seed']} | {r['lab_bank']} | {gap} |")
    md.append('')

red = [r['topic'] for r in board if r['answerable'] == 0 and r['bk_candidate'] == 0]
orange = [r['topic'] for r in board if r['answerable'] == 0 and r['bk_candidate'] > 0]
md += ['## 缺口结论',
       '',
       f'- 🔴 **完全没有题源**（{len(red)}）：' + ('、'.join(red) if red else '无'),
       f'- 🟠 **有教材题面但零答案**（{len(orange)}）：' + ('、'.join(orange) if orange else '无'),
       '',
       '## 数据源与口径',
       '',
       f"- 教材题面：`题库/教材习题.json`，{len(rows)} 条记录，分层来自 `题库/考研相关性.json`"
       f"（方法 `{relevance['method']}`）。",
       f'- 基础题：`题库/基础题库.json`，{len(basic)} 道原创题，含答案与易错点。',
       f'- PhysicsPrep 种子：`..\\PhysicsPrep\\data\\seed_questions.json`，'
       f'{len(json.loads((W / "data" / "seed_questions.json").read_text(encoding="utf-8")))} 道原创题'
       f'（经知识树 topic_ids 映射到细目名）。',
       f'- lab 题库：`..\\fastgpt-physics-lab\\bank\\questions.json`，10 道原创题（按 chapter 匹配）。',
       '- 大纲细目与考查要求：取自 `分析考研相关性.py` 的 rules，其页码指向根目录两份大纲 PDF。',
       '  **页码是大纲 PDF 的页序，未经与官方年度版本对照，仍需核对。**',
       '',
       '## 未匹配项',
       '',
       f'- PhysicsPrep 种子题未能映射到细目的：{len(prep_unmatched)}',
       json.dumps(prep_unmatched, ensure_ascii=False)[:600] or '无',
       f'- lab 题库未能映射到细目的：{len(lab_unmatched)}',
       json.dumps(lab_unmatched, ensure_ascii=False)[:400] or '无',
       '']

(T / '大纲覆盖看板.md').write_text('\n'.join(md), encoding='utf-8')
print('\n'.join(md[:12]))
print('...')
print(f'651 零可做题细目：{len([r for r in board if "651" in r["exams"] and r["answerable"] == 0])}')
print(f'803 零可做题细目：{len([r for r in board if "803" in r["exams"] and r["answerable"] == 0])}')
print('已写出 大纲覆盖看板.md / .json')
