"""设置、AI 连接测试、备份恢复与大纲归档视图。

密钥只从本地环境变量 / `.env` 读取：
界面可以修改 API Address、模型 ID、超时与重试次数，但**从不显示**完整密钥。
"""
import json
from pathlib import Path

ALLOWED_SUFFIXES = ('.pdf', '.json', '.txt', '.csv')


def mask_key(api_key):
    """只说明是否已配置；任何情况下都不回显密钥内容。

    短密钥尤其危险（例如 1-4 个字符时“显示末四位”等于完整泄露），
    因此这里对短于 12 个字符的密钥只报告长度。
    """
    if not api_key:
        return '未配置（将使用 Mock 模式）'
    if len(api_key) < 12:
        return f'已配置（长度仅 {len(api_key)}，内容不显示）'
    return f'已配置（长度 {len(api_key)}，末四位 ****{api_key[-4:]}）'


def mode_summary(settings, client=None):
    lines = []
    if settings is None:
        return '配置对象不可用。'
    if settings.effective_mock:
        reason = 'APP_MOCK_MODE=true' if settings.mock_mode else '缺少 API Key / Address / 模型 ID 之一'
        lines.append(f'**当前模式：Mock（离线可用）** · 原因：{reason}')
    else:
        lines.append('**当前模式：GenAI 在线（失败时自动回退 Mock）**')
    lines.append(f"- API Address：`{settings.base_url or '未配置'}`")
    lines.append(f'- 模型 ID：`{settings.model or "未配置"}`')
    chain = list(getattr(settings, 'models', ()) or ())
    if len(chain) > 1:
        lines.append('- 降级顺序：' + ' → '.join(f'`{name}`' for name in chain))
        lines.append('  （主模型因“模型不可用/无权限/请求被拒/限流/空内容”失败时依次尝试；'
                     '网络或认证错误不降级，直接回退 Mock）')
    elif not settings.effective_mock:
        lines.append('- 降级顺序：未配置（`GENAI_MODEL_FALLBACKS` 为空）')
    lines.append(f'- 超时：{settings.timeout} 秒 · 最大重试：{settings.max_retries}')
    lines.append(f'- API Key：{mask_key(settings.api_key)}')
    if client is not None:
        lines.append(f'- 客户端实现：`{getattr(client, "name", type(client).__name__)}`')
    return '\n'.join(lines)


def connection_report(client):
    """测试模型连接：明确区分在线成功、离线 Mock 与回退。

    关键点：在线失败时客户端会返回 `fallback_text=True` 的**替换内容**。
    这里不能把那坨内容当成“模型的回答”展示，否则界面会一边说“已回退 Mock”
    一边贴出一段看起来像模型输出的文字，反而更容易让人误判连通状态。
    """
    if client is None:
        return 'AI 客户端尚未就绪；固定题库、判分与学习记录仍可正常使用。'
    result = client.test_connection()
    mode = result.get('mode')
    fallback_text = result.get('fallback_text', False)
    text = result.get('text', '')
    served = result.get('model')

    if mode == 'online' and not result.get('error'):
        headline = '**连接成功（在线模型）**'
        chain = list(result.get('attempted_models') or ())
        if chain:
            headline += f' · 实际使用：`{served}`'
        body = text
        if len(chain) > 1:
            missed = '、'.join(f'`{name}`' for name in chain[:-1])
            body = f'（{missed} 不可用，已降级到 `{served}`）\n\n{body}'
    elif result.get('error'):
        headline = f'**在线调用失败，已回退 Mock** · 原因类别：`{result["error"]}`'
        attempted = list(result.get('attempted_models') or ())
        if attempted:
            headline += f' · 已尝试 {len(attempted)} 个模型'
        body = ('未取得模型输出。以下固定题库内容与判分功能不受影响，'
                '排查顺序：网络可达性 → API Address → 模型 ID → 密钥有效期。')
        if attempted and len(attempted) > 1:
            body = (f'已按顺序尝试：{" → ".join(f"`{name}`" for name in attempted)}。\n\n' + body)
        if not fallback_text:
            body = f'{body}\n\n{text}'
    else:
        headline = '**当前为 Mock 模式（未发起在线请求）**'
        # Mock 的 connection 文本本身就是身份说明，可以原样显示。
        body = text if not fallback_text or 'Mock' in text else ''
    return f'{headline}\n\n{body}'.rstrip()


def describe_import_errors(errors):
    if not errors:
        return ''
    return '\n'.join(f'- {item}' for item in errors)


def backup_help(database_path):
    return (
        '### 数据备份与恢复\n'
        f'当前数据库：`{database_path}`\n\n'
        '- 备份文件是完整 SQLite 副本，含题库与学习记录，**不含** API 密钥；\n'
        '- 恢复会整体替换当前数据库，请先点“备份当前数据库”留一份；\n'
        '- 备份/恢复不做任何外部上传。'
    )


def syllabus_help(versions):
    if not versions:
        return '尚无已归档大纲。导入你已核对来源的文件后，系统按 SHA256 保留版本。'
    rows = ['| 版本标签 | 科目 | SHA256（前12位） | 文件 | 状态 |', '| --- | --- | --- | --- | --- |']
    for item in versions:
        rows.append('| {label} | {subject} | {sha} | {file} | {status} |'.format(
            label=item.get('label', ''), subject=item.get('subject') or '—',
            sha=str(item.get('sha256', ''))[:12], file=item.get('file', ''),
            status=item.get('official_status', '')))
    rows.append('\n> 归档只代表“你导入了这个文件”，不代表它是某个年度的官方大纲。'
                '系统不会把未经核对的文件认定为考试大纲。')
    return '\n'.join(rows)
