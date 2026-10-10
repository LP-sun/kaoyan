from html import escape
import plotly.graph_objects as go


def dashboard_view(data):
    due = data.get('due_reviews', [])
    due_count = due if isinstance(due, int) else len(due)
    accuracy = data.get('seven_day_accuracy')
    accuracy_text = '尚无记录' if accuracy is None else f'{accuracy * 100:.0f}%' if accuracy <= 1 else f'{accuracy:.0f}%'
    cards = [('今日作答', data.get('today_count', 0)), ('近七天正确率', accuracy_text), ('待复习考点', due_count), ('学习方式', '本地持久化')]
    html = '<div class="stats-grid">' + ''.join(f'<div class="stat-card"><span>{escape(str(k))}</span><strong>{escape(str(v))}</strong></div>' for k, v in cards) + '</div>'
    daily = data.get('daily_counts', [])
    if isinstance(daily, dict):
        xs, ys = list(daily), list(daily.values())
    else:
        xs = [str(d.get('date', d.get('day', ''))) for d in daily]
        ys = [d.get('count', d.get('attempts', 0)) for d in daily]
    fig = go.Figure(go.Bar(x=xs, y=ys, marker_color='#5979ed'))
    fig.update_layout(title='最近七天 · 每日练习', height=260, margin=dict(l=35,r=20,t=45,b=35), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis_title='题数')
    weak = data.get('weak_topics', [])
    lines = ['### 今日建议', '先完成到期复习，再进行一次短诊断。掌握度是可解释的启发式估计，不是考试分数预测。']
    if weak:
        lines += ['\n**优先巩固**'] + [f"- {x.get('name', x.get('topic_name', x.get('topic_id', '')))}：掌握估计 {x.get('estimate', x.get('mastery', '未知'))}" for x in weak[:6]]
    else:
        lines.append('\n尚无足够证据，开始诊断以建立你的知识画像。')
    lines.append('\n### 最近诊断\n' + ('\n'.join(f'- {s}' for s in data.get('recent_sessions', [])[:3]) or '尚未开始'))
    return html, fig, '\n'.join(lines)
