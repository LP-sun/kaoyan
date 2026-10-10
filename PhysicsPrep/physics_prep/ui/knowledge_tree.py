"""知识树视图与编辑。

掌握度按用户单独存储（`mastery_records`），知识点定义里不带掌握度；
界面上的“未知”表示证据不足，而不是“已掌握”或“完全不会”。
"""
import json

MASTERY_UNKNOWN = '未知（证据不足）'


def mastery_text(value):
    if value is None:
        return MASTERY_UNKNOWN
    try:
        return f'{float(value):.2f}'
    except (TypeError, ValueError):
        return MASTERY_UNKNOWN


def tree_choices(service):
    """下拉选项：知识点名称 + 稳定 ID。"""
    return [('不限知识点', '')] + [
        (f"{t.get('name', t['id'])} · {t['id']}", t['id']) for t in service.topic_tree()]


def tree_rows(service):
    """知识树表格：稳定 ID、名称、父节点、前置知识、掌握度。"""
    rows = []
    for topic in service.topic_tree():
        rows.append([
            topic['id'],
            topic.get('name', ''),
            topic.get('parent_id') or '',
            ', '.join(topic.get('prerequisite_ids', [])),
            mastery_text(topic.get('mastery')),
        ])
    return rows


def tree_markdown(service):
    """按层级缩进展示知识树，便于确认结构而不是只看平面表格。"""
    topics = service.topic_tree()
    children = {}
    for topic in topics:
        children.setdefault(topic.get('parent_id'), []).append(topic)

    lines = []

    def walk(parent_id, depth):
        for topic in sorted(children.get(parent_id, []), key=lambda t: t['id']):
            indent = '  ' * depth
            mastery = mastery_text(topic.get('mastery'))
            lines.append(f'{indent}- **{topic.get("name", topic["id"])}** `{topic["id"]}` · 掌握度 {mastery}')
            walk(topic['id'], depth + 1)

    walk(None, 0)
    return '\n'.join(lines) if lines else '知识树为空。'


def export_tree(service, path):
    """导出知识点定义（不含掌握度），便于版本管理与再导入。"""
    values = [{k: v for k, v in topic.items() if k != 'mastery'} for topic in service.topic_tree()]
    from pathlib import Path
    path = Path(path)
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)


def topic_json_template():
    return json.dumps({
        'id': 'CUSTOM-001',
        'name': '自定义知识点',
        'parent_id': None,
        'prerequisite_ids': [],
        'difficulty': 2,
        'source_references': [],
    }, ensure_ascii=False, indent=2)
