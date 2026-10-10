"""汇总 deepseek相关性分析.json 的相关性评估，生成人读报告。

只读分析文件，不修改任何题库数据。缺 relevance 的记录按「未评估」计数。
输出：资料整理/题库/相关性评估报告.md 与终端摘要。

用法：
    python 资料整理/题库/汇总相关性评估.py
"""
from __future__ import annotations
import json
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "资料整理" / "题库"
SRC = OUT / "deepseek相关性分析.json"

LEVELS = ["high", "medium", "low", "none"]
BOOK_NAME = {
    "BK01": "光学2004", "BK04": "力学2004第二版", "BK05": "电磁学2006第二版",
    "BK06": "量子物理2008第二版", "BK07": "热学2005第二版", "BK08": "量子物理2001第一版",
}


def main() -> None:
    rows = json.loads(SRC.read_text(encoding="utf-8-sig"))
    total = len(rows)
    evaluated = [r for r in rows if r.get("relevance")]
    n_eval = len(evaluated)

    lvl = Counter(r["relevance"].get("level") for r in evaluated)
    books = defaultdict(lambda: Counter())
    exams = Counter()
    fit_counter = Counter()
    topic_counter = Counter()
    risks = Counter()
    rel_scores = []
    for r in evaluated:
        rel = r["relevance"]
        books[r.get("book", "?")][rel.get("level")] += 1
        rel_scores.append(rel.get("relevant", 0))
        for e in rel.get("exam_fit", []) or []:
            exams[str(e)] += 1
        for t in rel.get("topic_tags", []) or []:
            topic_counter[t] += 1
        for rk in rel.get("risk", []) or []:
            risks[rk] += 1

    def pct(n):
        return f"{n / n_eval * 100:.1f}%" if n_eval else "—"

    avg = (sum(rel_scores) / n_eval) if n_eval else 0
    lines = [
        "# 相关性评估报告（模型判断，非人工核验）",
        "",
        "> 数据来自 `deepseek相关性分析.json` 的 `relevance` 字段，由 `构建题库与推荐.py --deepseek` 生成。",
        "> 这是**模型判断**，仅供筛选参考；不能替代原页逐题人工核验。",
        "",
        f"- 记录总数：{total}",
        f"- 已评估（有 relevance）：{n_eval}（{n_eval / total * 100:.1f}%）",
        f"- 未评估：{total - n_eval}",
        f"- relevant 平均分：{avg:.1f} / 100",
        "",
        "## 价值层级分布（已评估部分）",
        "",
        "| 层级 | 数量 | 占比 |",
        "| --- | ---: | ---: |",
    ]
    for lv in LEVELS:
        lines.append(f"| {lv} | {lvl.get(lv, 0)} | {pct(lvl.get(lv, 0))} |")
    lines += ["", "## 各教材层级分布", "", "| 教材 | 已评估 | high | medium | low | none |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for bk in sorted(books):
        c = books[bk]
        lines.append(f"| {BOOK_NAME.get(bk, bk)} | {sum(c.values())} | {c.get('high',0)} | {c.get('medium',0)} | {c.get('low',0)} | {c.get('none',0)} |")

    lines += ["", "## 考试适配命中", "", "| 科目 | 命中题数 |", "| --- | ---: |"]
    for ex in sorted(exams):
        lines.append(f"| {ex} | {exams[ex]} |")

    lines += ["", "## 高频主题标签（前 20）", ""]
    for t, n in topic_counter.most_common(20):
        lines.append(f"- {t}：{n}")
    if risks:
        lines += ["", "## 模型标注的风险（前 10）", ""]
        for rk, n in risks.most_common(10):
            lines.append(f"- {rk}：{n}")

    report = "\n".join(lines) + "\n"
    (OUT / "相关性评估报告.md").write_text(report, encoding="utf-8")
    print(json.dumps({
        "total": total, "evaluated": n_eval, "level": dict(lvl),
        "avg_relevant": round(avg, 1), "exam_fit": dict(exams),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
