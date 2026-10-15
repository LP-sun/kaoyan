"""Single-card continuous practice view, backed by PracticeSessionController."""
import functools
import gradio as gr
from .quiz import render_question, feedback_text, LATEX
from .knowledge_tree import tree_choices
from ..services.practice import PracticeSessionController, ERROR_TYPES


def mount_practice(service, client_factory=None):
    controller = PracticeSessionController(service,client_factory)

    def safe(fn):
        @functools.wraps(fn)
        def call(*args):
            try:
                return fn(*args)
            except ValueError as exc:
                raise gr.Error(str(exc)[:250]) from None
            except Exception:
                raise gr.Error('操作未完成，学习状态已保留；请重试或继续刷题。') from None
        return call

    def summary_text(view):
        r=view['summary']; state=view['state']
        return (f"本轮作答 {r['attempts']} 题 · 独立正确 {r['independent_correct']} 题 / 独立尝试 {r['independent_attempts']} 题\n\n"
            f"过于简单跳过 {r.get('too_easy_count',0)} 题（不计成绩）\n\n"
            f"作答窗口累计 {state['elapsed_seconds']/60:.1f} 分钟（不是专注时间测量）\n\n"
            f"仍需无提示复测：{'、'.join(r['needs_independent_retest']) or '尚无待确认错误；仍按计划延迟复测'}\n\n"
            f"题目覆盖缺口：{'、'.join(r.get('coverage_gaps',[])) or '本轮未发现不可出题的指定考点'}\n\n{r['next_suggestion']}")

    def side_text(view):
        st=view['state']; remedy=view['remedy']
        names={t['id']:t for t in service.repository.topic_tree()}
        q=view.get('question') or {}
        pre=[p for t in q.get('topic_ids',[]) for p in names.get(t,{}).get('prerequisite_ids',[])]
        mode_name={'adaptive':'自适应刷题','foundation':'从基础开始','chapter':'指定章节','weakness':'错题补弱','review':'到期复习'}.get(st['mode'],st['mode'])
        phase_name={'READY':'准备开始','QUESTION':'独立练习','ANSWERING':'继续尝试','FEEDBACK':'本题反馈','REMEDIATION':'基础补救','VERIFICATION':'变式验证','SAVED':'已保存'}.get(st['phase'],st['phase'])
        weak=service.dashboard()['weak_topics'][:3]
        weakness='、'.join(x['name'] for x in weak) or '需要继续诊断'
        return (f"**模式：** {mode_name} · **阶段：** {phase_name}\n\n"
            f"**薄弱或证据不足：** {weakness}\n\n"
            f"**先修知识：** {'、'.join(names.get(t,{}).get('name',t) for t in pre) or '本题未标注先修节点'}\n\n"
            f"**补救目标：** {names.get(remedy.get('target'),{}).get('name','暂无')}\n\n"
            f"**下一题理由：** {view['next_reason'] or q.get('recommendation_reason','根据基础水平与考点覆盖选择')}\n\n"
            f"{st.get('notice','')}\n\n提示后正确仍需要无提示复测，不把当天重复正确视为长期掌握。")

    def render(view):
        values=list(render_question(None if view['state']['phase']=='SAVED' else view.get('question'),view['session_id']))
        if view.get('guidance'):
            values[8]=view['guidance']
        state=view['state']; report=view['summary']
        values[3] += f"\n\n本轮 {report['attempts']} 题 · 独立正确 {report['independent_correct']} · 作答窗口 {state['elapsed_seconds']/60:.1f} 分钟"
        if report.get('independent_accuracy') is not None:
            values[3] += f" · 独立正确率 {report['independent_accuracy']:.0%}（排除无法确认）"
        q=view.get('question') or {}
        if q.get('allowed_symbols'):
            values[3] += '\n\n可用符号：'+', '.join(q['allowed_symbols'])+'；注意大小写，可省略无歧义的符号间乘号，乘方用**。'
        if state['phase'] in ('FEEDBACK','SAVED'):
            values[10]=gr.update(interactive=False)
            values[11]=gr.update(interactive=False)
            values[12]=gr.update(interactive=state['phase']=='FEEDBACK')
            if state.get('last_feedback'):
                values[9]=feedback_text(state['last_feedback'])[0]
        elif state.get('notice'):
            values[9]=state['notice']
        return (*values,side_text(view),summary_text(view),'',
            gr.update(interactive=bool(q) and state['phase'] not in ('FEEDBACK','SAVED')),
            gr.update(value=state.get('question_filter','all')))

    def practice_start(subject,mode,chapter,question_filter='all'):
        return render(controller.start(subject,mode,chapter or None,question_filter))

    def practice_too_easy(sid,qid):
        if not sid: raise ValueError('请先开始刷题。')
        return render(controller.too_easy(sid,qid))

    def practice_filter(sid,question_filter):
        view=controller.set_question_filter(sid,question_filter)
        return render(view) if view else tuple(gr.update() for _ in outputs)

    def practice_continue():
        view=controller.resume()
        return render(view or controller.start())

    def practice_next(sid):
        if not sid: raise ValueError('请先开始刷题。')
        return render(controller.next(sid))

    def practice_submit(sid,qid,token,one,many,text):
        answer=one if one is not None else many if many else text
        if answer in (None,'',[]):
            raise ValueError('请先作答；不会时点击提示。')
        view=controller.submit(sid,qid,answer,token)
        return render(view)

    def practice_hint(sid,qid):
        return controller.hint(sid,qid)['teacher']

    def practice_solution(sid,qid):
        return controller.hint(sid,qid,full=True)['teacher']

    def practice_question(sid,qid,text):
        if not text.strip(): raise ValueError('请输入针对本题的问题。')
        from ..services.tutor import classify
        result=controller.hint(sid,qid,text=text)
        return (result['teacher'],gr.update(interactive=True) if classify(text)=='report' or result.get('submitted') else gr.update(),
            gr.update(interactive=False) if result.get('submitted') else gr.update(),
            gr.update(interactive=False) if result.get('submitted') or classify(text)=='report' else gr.update())

    def practice_finish(sid):
        if not sid: raise ValueError('请先开始刷题。')
        return render(controller.finish(sid))

    def practice_error(sid,category):
        return render(controller.record_error(sid,category))

    def practice_retry(sid):
        return render(controller.try_again(sid))

    def practice_remediate(sid):
        return render(controller.remediate_now(sid))

    with gr.Tab('连续刷题',id='practice'):
        sid=gr.State(None); qid=gr.State(None); token=gr.State(None)
        with gr.Row():
            subject=gr.Dropdown([('自动安排','auto'),('651 普通物理','general'),('803 量子力学','quantum')],value='auto',label='科目')
            mode=gr.Dropdown([('自适应刷题','adaptive'),('从基础开始','foundation'),('指定章节','chapter'),('错题补弱','weakness'),('到期复习','review')],value='adaptive',label='模式')
            question_filter=gr.Dropdown([('全部题型','all'),('只做选择题','choice')],value='all',label='题型',elem_id='practice-type-filter')
            begin=gr.Button('开始刷题',variant='primary',elem_id='practice-start')
            resume=gr.Button('继续刷题',elem_id='practice-continue')
        with gr.Accordion('可选：指定章节',open=False):
            chapter=gr.Dropdown(tree_choices(service),value='',label='章节 / 知识点')
        with gr.Row():
            with gr.Column(scale=3):
                stem=gr.Markdown('### 准备开始\n点击「开始刷题」，在这里查看题目并作答。',latex_delimiters=LATEX,elem_id='practice-card')
                radio=gr.Radio([],visible=False,label='单选',elem_id='practice-radio')
                many=gr.CheckboxGroup([],visible=False,label='多选',elem_id='practice-many')
                answer=gr.Textbox(visible=False,lines=3,label='答案',placeholder='例如 sqrt(2*g*h)，乘号用*，幂用**',elem_id='practice-answer')
                with gr.Row():
                    submit=gr.Button('提交答案',variant='primary',interactive=False,elem_id='practice-submit')
                    hint_btn=gr.Button('不会 / 提示',interactive=False,elem_id='practice-hint-button')
                    next_btn=gr.Button('下一题',interactive=False,elem_id='practice-next')
                    easy_btn=gr.Button('本题过于简单',interactive=False,elem_id='practice-too-easy')
                with gr.Accordion('题目信息与推荐理由',open=False):
                    metadata=gr.Markdown('点击开始刷题，系统会自动选择下一道题。',elem_id='practice-meta')
                with gr.Accordion('更多操作',open=False):
                    with gr.Row():
                        solution_btn=gr.Button('查看解析',elem_id='practice-solution-button')
                        retry=gr.Button('本题继续尝试（不作为变式验证）')
                        remediate=gr.Button('完全没思路：先补基础')
                hint=gr.Markdown(latex_delimiters=LATEX,elem_id='practice-hint')
                feedback=gr.Markdown(latex_delimiters=LATEX,elem_id='practice-feedback')
                solution=gr.Markdown(latex_delimiters=LATEX)
                with gr.Accordion('针对当前题目提问',open=False):
                    prompt=gr.Textbox(label='哪里卡住了？',placeholder='不知道用什么公式 / 这一步为什么')
                    ask=gr.Button('解释这一点')
                with gr.Accordion('可选：修改本题错因',open=False):
                    error_type=gr.Dropdown(list(ERROR_TYPES),value='暂无法确定',label='我认为的错误原因')
                    error_btn=gr.Button('保存错因')
            with gr.Column(scale=1):
                with gr.Accordion('学习路线',open=False):
                    side=gr.Markdown(elem_id='practice-sidebar')
                with gr.Accordion('本轮统计',open=False):
                    summary=gr.Markdown(elem_id='practice-summary')
                end=gr.Button('结束会话',elem_id='practice-end')
        outputs=[sid,qid,token,metadata,stem,radio,many,answer,hint,feedback,submit,hint_btn,next_btn,side,summary,solution,easy_btn,question_filter]
        begin.click(safe(practice_start),[subject,mode,chapter,question_filter],outputs,concurrency_limit=1)
        question_filter.input(safe(practice_filter),[sid,question_filter],outputs,concurrency_limit=1)
        easy_btn.click(safe(practice_too_easy),[sid,qid],outputs,concurrency_limit=1)
        resume.click(safe(practice_continue),outputs=outputs,concurrency_limit=1)
        next_btn.click(safe(practice_next),[sid],outputs,concurrency_limit=1)
        submit.click(safe(practice_submit),[sid,qid,token,radio,many,answer],outputs,concurrency_limit=1)
        hint_btn.click(safe(practice_hint),[sid,qid],[hint],concurrency_limit=1)
        solution_btn.click(safe(practice_solution),[sid,qid],[solution],concurrency_limit=1)
        ask.click(safe(practice_question),[sid,qid,prompt],[hint,next_btn,submit,easy_btn],concurrency_limit=1)
        end.click(safe(practice_finish),[sid],outputs,concurrency_limit=1)
        error_btn.click(safe(practice_error),[sid,error_type],outputs,concurrency_limit=1)
        retry.click(safe(practice_retry),[sid],outputs,concurrency_limit=1)
        remediate.click(safe(practice_remediate),[sid],outputs,concurrency_limit=1)
    return controller
