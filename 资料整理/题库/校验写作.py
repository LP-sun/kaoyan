"""校验人工写作记录（资料整理/题库/写作/<教材ID>/<题目ID>.json）。

只读校验，不修改任何文件。退出码 0 表示全部通过，1 表示存在错误。
约定与字段含义见根目录《题库写作指南.md》。设计原则：
- 人工记录必须能对应到原始提取记录（稳定 ID），否则报错；
- 不强制要求题面/解答已完成（状态可为 draft/not_started），但字段结构必须合法；
- 状态与内容的一致性做强校验：题面标 verified 必须能追溯到原页；解答标 checked 必须有检验方法。

用法：
    python 资料整理/题库/校验写作.py            # 校验，打印报告
    python 资料整理/题库/校验写作.py --json     # 只输出 JSON 结果
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
QDIR = ROOT / "资料整理" / "题库"
WRITE = QDIR / "写作"
CANON = QDIR / "教材习题.json"          # 聚合题库，用于核对稳定 ID
BOOK_DIR = ROOT / "资料整理" / "教材习题"  # 分教材原始记录

STATEMENT_STATUS = {"draft", "verified", "needs_review"}
SOLUTION_STATUS = {"not_started", "draft", "checked", "needs_review"}
ORIGIN = {"original_derivation", "reference_adapted", "reference_verbatim"}

ID_RE = re.compile(r"^(BK\d{2})-(思考题|习题|附录习题)-[\w\u4e00-\u9fff\-]+$")


def load_known_ids() -> set[str]:
    """以聚合题库为准；若不存在则退回分教材记录，保证脚本可独立运行。"""
    if CANON.exists():
        return {q["id"] for q in json.loads(CANON.read_text(encoding="utf-8"))}
    ids: set[str] = set()
    for f in BOOK_DIR.glob("*/习题.json"):
        ids |= {q["id"] for q in json.loads(f.read_text(encoding="utf-8"))}
    return ids


def check_record(path: Path, rec: dict, sid: str, known: set[str]) -> list[str]:
    errs: list[str] = []
    e = lambda m: errs.append(f"{sid}: {m}")

    if rec.get("id") != sid:
        e(f"id 字段（{rec.get('id')!r}）与文件名（{sid}）不一致")
    if sid not in known:
        e("稳定 ID 在原始提取记录中不存在（不得虚构题目）")
    if not ID_RE.match(sid):
        e("ID 格式异常，应为 BKxx-思考题/习题/附录习题-...")
    if rec.get("book_id") and sid.split("-")[0] != rec["book_id"]:
        e("book_id 与 ID 前缀不一致")

    st = rec.get("statement")
    if st is not None and not isinstance(st, str):
        e("statement 必须是字符串")
    figs = rec.get("figures", [])
    if not isinstance(figs, list):
        e("figures 必须是数组")
    topics = rec.get("syllabus_topics", [])
    if not isinstance(topics, list):
        e("syllabus_topics 必须是数组")

    srcs = rec.get("sources")
    if srcs is not None:
        if not isinstance(srcs, list) or not srcs:
            e("sources 必须是非空数组（需能追溯到原页）")
        else:
            for i, s in enumerate(srcs):
                if not isinstance(s, dict) or "pdf_page" not in s:
                    e(f"sources[{i}] 缺少 pdf_page")
                    continue
                pp = s.get("pdf_path")
                if pp and not (ROOT / pp).exists():
                    e(f"sources[{i}].pdf_path 指向的文件不存在：{pp}")

    sol = rec.get("solution", {})
    if not isinstance(sol, dict):
        e("solution 必须是对象")
    else:
        org = sol.get("origin")
        if org is not None and org not in ORIGIN:
            e(f"solution.origin 取值非法：{org!r}（允许 {sorted(ORIGIN)}）")
        for k in ("assumptions", "steps", "checks", "common_errors"):
            if k in sol and not isinstance(sol[k], list):
                e(f"solution.{k} 必须是数组")

    rev = rec.get("review")
    if not isinstance(rev, dict):
        e("缺少 review 对象（需含 statement_status / solution_status）")
        return errs
    ss, cs = rev.get("statement_status"), rev.get("solution_status")
    if ss not in STATEMENT_STATUS:
        e(f"review.statement_status 非法：{ss!r}（允许 {sorted(STATEMENT_STATUS)}）")
    if cs not in SOLUTION_STATUS:
        e(f"review.solution_status 非法：{cs!r}（允许 {sorted(SOLUTION_STATUS)}）")
    if not rev.get("updated_at") or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(rev.get("updated_at", ""))):
        e("review.updated_at 需为 YYYY-MM-DD")
    if not isinstance(rev.get("issues", []), list):
        e("review.issues 必须是数组")

    # 状态—内容一致性（强校验）
    if ss == "verified":
        if not st or not st.strip():
            e("题面标记 verified，但 statement 为空")
        if not srcs:
            e("题面标记 verified，但没有 sources，无法追溯原页核验")
        if not (rev.get("method") or "").strip():
            e("题面标记 verified，但 review.method 为空（需记录核验方法）")
    if cs == "checked":
        if not sol or not sol.get("final_answer"):
            e("解答标记 checked，但 solution.final_answer 为空")
        if not (sol.get("checks") or []):
            e("解答标记 checked，但 solution.checks 为空（需记录检验方法）")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args()

    known = load_known_ids()
    if not WRITE.exists():
        result = {"writing_dir": str(WRITE.relative_to(ROOT)).replace("\\", "/"),
                  "records": 0, "books": {}, "errors": [], "ok": True,
                  "note": "写作目录尚不存在，尚无人工写作记录"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    files = sorted(WRITE.rglob("*.json"))
    files = [f for f in files if f.name not in {"README.json", "_模板.json"}]
    errors: list[str] = []
    seen: dict[str, Path] = {}
    books = Counter()
    st_counter = Counter()
    sol_counter = Counter()
    for f in files:
        sid = f.stem
        rel = f.relative_to(ROOT)
        if sid in seen:
            errors.append(f"{sid}: 重复记录，同时出现在 {seen[sid]} 与 {rel}")
            continue
        seen[sid] = rel
        # 目录名应与教材 ID 一致
        if f.parent.name != sid.split("-")[0]:
            errors.append(f"{sid}: 所在目录 {f.parent.name} 与教材 ID 前缀不一致")
        try:
            rec = json.loads(f.read_text(encoding="utf-8-sig"))  # 容忍 Windows 编辑器写入的 BOM
        except Exception as ex:
            errors.append(f"{sid}: JSON 解析失败：{ex}")
            continue
        errors += check_record(f, rec, sid, known)
        books[sid.split("-")[0]] += 1
        rev = rec.get("review", {})
        st_counter[rev.get("statement_status")] += 1
        sol_counter[rev.get("solution_status")] += 1

    result = {
        "writing_dir": str(WRITE.relative_to(ROOT)).replace("\\", "/"),
        "records": len(files),
        "books": dict(sorted(books.items())),
        "statement_status": dict(st_counter),
        "solution_status": dict(sol_counter),
        "errors": errors,
        "ok": not errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
