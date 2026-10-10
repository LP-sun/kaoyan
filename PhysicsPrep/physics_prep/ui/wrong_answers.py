"""错题本与复习计划视图。

每次提交都在 `attempts` 里留下独立记录（含题目快照与判分反馈），
因此同一道题的历次作答可以并排比较。
"""
import json

from ..clock import to_iso


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _answer_text(answer):
    if isinstance(answer, (list, tuple)):
        return '、'.join(str(x) for x in answer)
    if answer is None:
        return ''
    return str(answer)


def wrong_rows(service, topic_id=None):
    """错题表格行：题目 ID、作答时间、原题、你的答案、结果、标准答案、解析。"""
    rows = []
    for item in service.wrong_answers(topic_id or None):
        snapshot = _as_dict(item.get('snapshot')) or item
        feedback = _as_dict(item.get('feedback'))
        status = feedback.get('status') or item.get('status', '')
        label = {'incorrect': '错误', 'uncertain': '待人工确认'}.get(status, status)
        rows.append([
            item.get('question_id', snapshot.get('id', '')),
            item.get('created_at', ''),
            snapshot.get('stem', item.get('stem', '')),
            _answer_text(item.get('answer')),
            label,
            str(feedback.get('correct_answer', snapshot.get('correct_answer', ''))),
            str(feedback.get('solution', snapshot.get('solution', ''))),
        ])
    return rows


def attempt_history(service, question_id):
    """同一道题的历次作答，用于对比“这次和上次哪里变了”。"""
    rows = []
    with service.factory() as session:
        from sqlalchemy import select
        from ..database.models import Attempt
        records = list(session.scalars(select(Attempt).where(
            Attempt.user_id == service.user_id,
            Attempt.question_id == question_id,
        ).order_by(Attempt.id)))
    for record in records:
        feedback = _as_dict(record.feedback)
        rows.append({
            'attempt_id': record.id,
            'created_at': to_iso(record.created_at),
            'answer': _answer_text(record.answer),
            'status': record.status,
            'error_category': feedback.get('error_category', ''),
        })
    return rows


def plan_markdown(service):
    """复习计划：到期考点 + 最近诊断记录 + 下次复习时间。"""
    data = service.dashboard()
    due = data.get('due_reviews') or []
    lines = ['### 到期复习']
    if due:
        lines += [f"- {item['name']}（{item['topic_id']}）· 到期时间 {item['due_at']}" for item in due]
    else:
        lines.append('暂无到期复习。完成诊断后，系统会按表现安排间隔复习。')

    mastery = sorted([m for m in data.get('mastery', []) if m.get('estimate') is not None],
                     key=lambda m: m['estimate'])
    lines.append('\n### 待巩固考点（掌握度升序）')
    if mastery:
        for item in mastery[:8]:
            lines.append(
                f"- {item['name']}：掌握度 {item['estimate']:.2f} · 作答 {item['attempts']} 次 · "
                f"正确 {item['correct']} 次 · 最近练习 {item.get('last_practiced') or '—'}")
    else:
        lines.append('尚无作答证据。')

    lines.append('\n### 本轮诊断记录')
    history = service.history()[:8]
    lines += [f"- {item['started_at']} · {item['subject'] or '全部科目'} · {item['status']}" for item in history] or ['- 尚未开始']
    lines.append('\n> 复习间隔是按表现启发式安排的，不是经过校准的记忆模型预测。')
    return '\n'.join(lines)


def wrong_summary(service, topic_id=None):
    rows = wrong_rows(service, topic_id)
    if not rows:
        return '当前没有错题记录。答错的题会自动出现在这里，可随时重做并对比历次作答。'
    return f'共 {len(rows)} 条错题记录。选择“重新练习这道题”会新建一次诊断，保留原有记录以便对比。'
