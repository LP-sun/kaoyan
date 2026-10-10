"""题型分类、DeepSeek 相关性分析和推荐参数生成。

默认只做可复现的本地分类；传 --deepseek 才会调用兼容 OpenAI Chat
Completions 的 DeepSeek 端点。密钥只从环境变量读取，不写入输出文件。
"""
from __future__ import annotations
import argparse, json, os, re, time
from pathlib import Path
from collections import Counter
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
QPATH = ROOT / "资料整理" / "题库" / "教材习题.json"
OUT = ROOT / "资料整理" / "题库"

TYPE_RULES = {
    "conceptual": ("概念判断", "概念、定义、定律、现象解释"),
    "formula": ("公式辨析", "公式适用条件、单位、数量级或公式选择"),
    "calculation": ("定量计算", "需要代数、数值或多步推导"),
    "derivation": ("推导证明", "证明、推导、说明关系或从基本定律推出结论"),
    "application": ("综合应用", "情境分析、实验设计、图像或跨章节应用"),
    "open": ("开放论述", "开放性讨论、解释或无法唯一判分的问答"),
}

def classify(q: dict) -> dict:
    text = q.get("question_ocr", "")
    t = text.replace(" ", "")
    if any(x in t for x in ("证明", "推导", "导出", "推得", "说明为什么")):
        kind = "derivation"
    elif any(x in t for x in ("计算", "求", "求出", "多少", "数值", "速度", "能量", "电流", "电势")) and any(c.isdigit() for c in t):
        kind = "calculation"
    elif any(x in t for x in ("单位", "量纲", "适用条件", "能否使用", "正确的是", "错误的是")):
        kind = "formula"
    elif any(x in t for x in ("实验", "装置", "现象", "图像", "应用", "测量", "设计")):
        kind = "application"
    elif any(x in t for x in ("为什么", "何谓", "定义", "定律", "概念", "意义", "解释")):
        kind = "conceptual"
    else:
        kind = "open" if q.get("type") == "思考题" else "conceptual"
    objective = kind in {"conceptual", "formula", "calculation"}
    return {"question_type": kind, "question_type_label": TYPE_RULES[kind][0],
            "objective": objective, "auto_grade": objective,
            "estimated_minutes": {"conceptual": 4, "formula": 6, "calculation": 12,
                                   "derivation": 15, "application": 10, "open": 8}[kind]}

def endpoint(base: str) -> str:
    """兼容三种写法：已含 /chat/completions、含 /v1、以及仅主机名。"""
    b = base.rstrip("/")
    if b.endswith("/chat/completions"):
        return b
    return b + "/chat/completions"

def call_deepseek(items: list[dict], base: str, key: str, model: str) -> list[dict]:
    prompt = """你是中国物理考研课程审核员。逐题判断题库题目对651普通物理或803量子力学复习的价值。只返回JSON数组，每项字段：id, relevant(0-100), level(one of high,medium,low,none), topic_tags(数组), exam_fit(数组651/803), reason(不超过45字), risk(数组，可为空), confidence(0-1)。依据考研大纲、典型考法和可迁移性；教材超纲、过度繁琐或信息不足要降低分数。不要臆造答案。\n题目："""
    payload = {"model": model, "temperature": 0.1, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt + json.dumps(items, ensure_ascii=False)}]}
    req = Request(endpoint(base), data=json.dumps(payload).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode())
    content = data["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.I).strip()
    # 容错：模型偶尔在数组外带解释文字，取第一个 [ 到最后一个 ]。
    a, b = content.find("["), content.rfind("]")
    if a != -1 and b != -1: content = content[a:b+1]
    return json.loads(content)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deepseek", action="store_true")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    qs = json.loads(QPATH.read_text(encoding="utf-8"))
    existing = {}
    rp = OUT / "deepseek相关性分析.json"
    if args.resume and rp.exists(): existing = {x["id"]: x for x in json.loads(rp.read_text(encoding="utf-8"))}
    rows = []
    for q in qs:
        c = classify(q)
        r = {"id": q["id"], "book": q.get("book"), "chapter": q.get("chapter"), "source_type": q.get("type"), **c}
        if q["id"] in existing: r.update(existing[q["id"]])
        rows.append(r)
    if args.deepseek:
        key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("GENAI_API_KEY")
        base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        if not key: raise SystemExit("缺少 DEEPSEEK_API_KEY 或 GENAI_API_KEY")
        by_id = {x["id"]: x for x in rows}
        done = {x["id"] for x in rows if x.get("relevance")}  # 只有已产出 relevance 才算已完成
        total_batches = (len(qs) + args.batch_size - 1) // args.batch_size
        for i in range(0, len(qs), args.batch_size):
            batch = [{"id": q["id"], "subject_hint": "量子" if q["book"].find("量子") >= 0 else "普物", "question": q["question_ocr"][:1600]} for q in qs[i:i+args.batch_size] if q["id"] not in done]
            if not batch: continue
            bn = i // args.batch_size + 1
            last_err = None
            for attempt in range(1, 4):  # 最多重试 3 次，避免瞬时网络错误中断长跑
                try:
                    got = call_deepseek(batch, base, key, model)
                    for a in got:
                        if a.get("id") in by_id:
                            by_id[a["id"]].update({"relevance": a})
                            done.add(a["id"])
                    print(f"批次 {bn}/{total_batches} 完成：本批 {len(batch)} 题，累计 {len(done)}/{len(qs)} 有 relevance", flush=True)
                    rp.write_text(json.dumps(list(by_id.values()), ensure_ascii=False, indent=2), encoding="utf-8")
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    print(f"批次 {bn}/{total_batches} 第 {attempt} 次失败: {e}", flush=True)
                    rp.write_text(json.dumps(list(by_id.values()), ensure_ascii=False, indent=2), encoding="utf-8")
                    time.sleep(2 * attempt)
            if last_err is not None:
                raise last_err
            time.sleep(0.3)
        rows = list(by_id.values())
        rp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    Counter_rows = Counter(x["question_type"] for x in rows)
    params = {"version": "recommend-v3", "weights": {"relevance": 0.32, "weakness": 0.25, "due": 0.20, "coverage": 0.13, "difficulty_fit": 0.06, "novelty": 0.04}, "objective_mix": {"conceptual": 0.25, "formula": 0.15, "calculation": 0.35, "derivation": 0.10, "application": 0.10, "open": 0.05}, "spaced_days": [1, 3, 7, 14, 30], "caps": {"same_topic_per_session": 3, "same_question_type_ratio": 0.6, "low_relevance_max_ratio": 0.1}, "classification_counts": Counter_rows}
    (OUT / "推荐参数v3.json").write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"questions": len(rows), "types": Counter_rows, "deepseek": sum("relevance" in x for x in rows)}, ensure_ascii=False))
if __name__ == "__main__": main()
