"""答题卡片与判分反馈的渲染。

安全约定：这里接收的 `question` 只包含 `LearningService._public()` 过滤后的字段，
标准答案与解析永远不会进入作答前的前端组件。
"""
import uuid
import gradio as gr

LATEX = [
    {'left': '$$', 'right': '$$', 'display': True},
    {'left': '$', 'right': '$', 'display': False},
    {'left': '\\(', 'right': '\\)', 'display': False},
    {'left': '\\[', 'right': '\\]', 'display': True},
]

TYPE_LABELS = {
    'single_choice': '单选题',
    'multiple_choice': '多选题',
    'numeric': '数值计算题',
    'symbolic': '符号表达式题',
    'short_answer': '简答 / 推导题',
}

STATUS_LABELS = {
    'correct': '✓ 正确',
    'incorrect': '✕ 需要巩固',
    'wrong': '✕ 需要巩固',
    'uncertain': '△ 需要人工确认',
}

SUBJECT_LABELS = {
    'mechanics': '力学',
    'electromagnetism': '电磁学',
    'thermodynamics': '热学',
    'waves_optics': '波动与光学',
    'quantum': '量子力学',
    'math_methods': '数学物理方法',
}


def _choice_pairs(question):
    options = question.get('options') or []
    if isinstance(options, dict):
        return [(f'{key}. {value}', key) for key, value in options.items()]
    return [(f'{chr(65 + index)}. {value}', chr(65 + index)) for index, value in enumerate(options)]


def render_question(question, session_id):
    """把一道题渲染成 (状态, 元信息, 题干, 各类作答控件, 按钮状态)。

    控件状态与题型一一对应，避免上一题的选项残留到下一题。
    """
    if not question:
        return (
            session_id, None, None,
            '本轮完成',
            '### 本轮题目已完成\n点击「查看本轮诊断报告」，或回到「学习总览」重新选择科目开始新一轮诊断。',
            gr.update(visible=False, value=None),
            gr.update(visible=False, value=[]),
            gr.update(visible=False, value=''),
            '', '',
            gr.update(interactive=False),
            gr.update(interactive=False),
            gr.update(interactive=False),
        )

    kind = question.get('question_type', 'short_answer')
    choices = _choice_pairs(question)
    subject = SUBJECT_LABELS.get(question.get('subject', ''), question.get('subject', ''))
    topics = ' / '.join(question.get('topic_names', question.get('topic_ids', [])))
    progress = question.get('session_progress')
    info = (
        f"**{subject}** · {topics}\n\n"
        f"题型 {TYPE_LABELS.get(kind, kind)} · 难度 {question.get('difficulty', '?')} / 5 · "
        f"题目 ID `{question.get('id', '')}`"
        + (f" · 本会话已完成 {progress} 题" if progress is not None else '')
    )
    reason = question.get('recommendation_reason')
    if reason:
        info += f'\n\n选题理由：{reason}'

    is_single = kind == 'single_choice'
    is_multiple = kind == 'multiple_choice'
    return (
        session_id,
        question['id'],
        uuid.uuid4().hex,
        info,
        question['stem'],
        gr.update(choices=choices, value=None, label='请选择一个选项', visible=is_single),
        gr.update(choices=choices, value=[], label='请选择全部正确选项', visible=is_multiple),
        gr.update(value='', label='你的计算结果 / 推导', visible=not (is_single or is_multiple)),
        '', '',
        gr.update(interactive=True),
        gr.update(interactive=True),
        gr.update(interactive=False),
    )


def feedback_text(feedback):
    """判分反馈：结果用文字说明，不只靠颜色；解析与作答区分开。"""
    status = feedback.get('status', 'uncertain')
    label = STATUS_LABELS.get(status, str(status))
    explanation = feedback.get('explanation', '')
    topics = feedback.get('topic_names') or []
    category = feedback.get('error_category', '尚无法确定')
    analysis = feedback.get('error_analysis', '')

    summary = [f'### {label}', explanation]
    if feedback.get('hint_level'):
        summary.append(f"**借助提示完成**（层级 {feedback['hint_level']}）：不计为独立正确证据，已安排无提示复测。")
    elif feedback.get('evidence_kind')=='original_revisit':
        summary.append('**原题回练**：不能替代不同题面验证或延迟独立复测。')
    if topics:
        summary.append(f'**关联知识点：** {"、".join(topics)}')
    summary.append(f'**错因判断：** {category}')
    if analysis:
        summary.append(f'{analysis}')
    if feedback.get('process_assessment'):
        advice=feedback['process_assessment']
        summary.append('**过程评估（模型建议，仍为暂无法确认）：** '+advice.get('next_action',''))
        issues=advice.get('possible_issues') or []
        if issues:
            summary.append('可能问题：'+'；'.join(issues))

    mastery = feedback.get('mastery') or []
    if mastery:
        rows = ['**掌握度更新（启发式估计，非已验证测量）：**']
        for item in mastery:
            estimate = item.get('estimate')
            shown = '未知' if estimate is None else f'{float(estimate):.2f}'
            rows.append(f"- `{item['topic_id']}` → {shown} · 累计作答 {item.get('attempts', 0)} 次 · 下次复习 {item.get('due_at', '—')}")
        summary.append('\n'.join(rows))
    if status == 'incorrect':
        summary.append('**建议复习：** 先回看该考点的前置知识，再用同考点的低难度题确认概念，最后回到本题重做。')
    elif status == 'uncertain':
        summary.append('**建议：** 系统暂无法确认。请按上方具体提示检查符号大小写、括号和乘号；有歧义时用 * 明确相乘，或点击「查看解析」自行比对。')

    detail = [f"### 标准答案\n{feedback.get('correct_answer', '需要进一步核对')}"]
    detail.append(f"### 推导与检验\n{feedback.get('solution', '本地题库暂无该题解析。')}")
    return '\n\n'.join(summary), '\n\n'.join(detail)
