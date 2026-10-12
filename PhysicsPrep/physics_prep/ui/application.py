"""UI 事件调用持久化服务；前端状态里不保存任何含答案的题目对象。

界面模块分工：
- `quiz.py`        答题卡片渲染与判分反馈文案
- `dashboard.py`   学习总览统计与图表
- `knowledge_tree.py` 知识树展示与导入导出
- `wrong_answers.py`  错题本与复习计划
- `settings.py`     AI 连接、备份恢复、大纲归档
"""
import functools
import json
import tempfile
from pathlib import Path
import gradio as gr
from .dashboard import dashboard_view
from .quiz import LATEX, render_question, feedback_text
from .styles import CSS
from .knowledge_tree import tree_choices, tree_rows, tree_markdown, export_tree, topic_json_template
from .wrong_answers import wrong_rows, plan_markdown, attempt_history, wrong_summary
from .settings import mode_summary, connection_report, backup_help, syllabus_help, mask_key

SUBJECTS = [('全部科目', ''), ('力学', 'mechanics'), ('电磁学', 'electromagnetism'), ('热学', 'thermodynamics'), ('波动与光学', 'waves_optics'), ('量子力学', 'quantum')]


def build_app(service, llm_factory=None, settings=None):
    from physics_prep.services.syllabus import SyllabusArchive
    from physics_prep.llm.prompts import tutor_system, HINT_FALLBACK
    syllabus = SyllabusArchive(Path(__file__).resolve().parents[2] / 'data' / 'syllabi')
    def safe(fn, name=None):
        """把服务异常转成界面可读的 gr.Error。

        保留原函数名（`functools.wraps` + 可选显式名），这样 Gradio 的事件注册表、
        `/api` 文档与测试都能按名字定位处理器，而不是一串 `wrapped_23`。
        """
        @functools.wraps(fn)
        def wrapped(*args):
            try:
                return fn(*args)
            except Exception as exc:
                # Service failures should be actionable without exposing secrets/config.
                if isinstance(exc, (ValueError, KeyError, TypeError)):
                    raise gr.Error(str(exc)[:350]) from None
                raise gr.Error('操作未完成，请检查本地服务日志或输入格式。') from None

        wrapped.__name__ = name or getattr(fn, '__name__', 'handler')
        return wrapped

    def topics_choices():
        return tree_choices(service)

    def start(subject, chapter):
        sid = service.start(subject=subject or None, chapter=chapter or None)
        return render_question(service.next(sid), sid)

    def redo(question_id):
        sid = service.start(question_id=question_id)
        return render_question(service.next(sid), sid)

    def advance(sid):
        if not sid:
            raise ValueError('请先开始诊断。')
        return render_question(service.next(sid), sid)

    def resume():
        sid = service.resume()
        if not sid:
            raise ValueError('暂无进行中的诊断，请选择科目开始。')
        return render_question(service.next(sid), sid)

    def submit(sid, qid, token, one, many, text):
        if not sid or not qid or not token:
            raise ValueError('请先开始诊断。')
        answer = one if one is not None else many if many else text
        if answer is None or answer == '' or answer == []:
            raise ValueError('请选择选项或输入答案。')
        feedback = service.submit(sid, qid, answer, token)
        summary, detail = feedback_text(feedback)
        return summary, detail, gr.update(interactive=False), gr.update(interactive=True)

    def reveal(qid, feedback):
        if not qid or not feedback:
            raise ValueError('先提交你的答案，再查看完整解析。作答前可以查看提示。')
        return feedback

    def tree_view():
        return tree_rows(service)

    def tree_structure():
        return tree_markdown(service)

    def wrong_view(topic):
        return wrong_rows(service, topic or None)

    def history_view(question_id):
        if not question_id:
            raise ValueError('请先填写题目 ID。')
        rows = attempt_history(service, question_id.strip())
        if not rows:
            return '这道题还没有作答记录。'
        lines = [f"### 题目 {question_id.strip()} 的历次作答",
                 '| 次数 | 时间 | 你的答案 | 结果 | 记录错因 |', '| --- | --- | --- | --- | --- |']
        for index, item in enumerate(rows, 1):
            lines.append(f"| {index} | {item['created_at']} | {item['answer']} | {item['status']} | {item['error_category']} |")
        lines.append('\n> 每次提交都是独立记录；题目被修改也不影响这里的历史快照。')
        return '\n'.join(lines)

    def question_list(subject, topic, difficulty, search):
        return [[q['id'],q.get('subject',''),','.join(q.get('topic_ids',[])),q.get('difficulty',''),q.get('question_type',''),q.get('source_type',''),str(q.get('verified',False)),q.get('stem','')] for q in service.list_questions(subject=subject or None, topic_id=topic or None, difficulty=int(difficulty) if difficulty else None, search=search or None)]

    def load_question(qid):
        found = [x for x in service.list_questions() if x['id']==qid]
        if not found: raise ValueError('题目 ID 不存在。')
        return json.dumps(found[0],ensure_ascii=False,indent=2)

    def save_question(raw):
        result = service.save_question(json.loads(raw))
        return '已保存题目。保留历史作答快照；未审核题目不进入正式诊断。'

    def save_topic(raw):
        service.save_topic(json.loads(raw))
        return '已保存知识点；依赖关系已由服务校验。', tree_view()

    def export_topics():
        path = Path(tempfile.mkdtemp(prefix='physicsprep-topics-')) / 'knowledge-tree.json'
        return export_tree(service, path)

    def export(kind):
        folder = Path(tempfile.mkdtemp(prefix='physicsprep-'))
        path = folder / ('questions.csv' if kind=='CSV' else 'questions.json')
        service.export_questions(str(path))
        return str(path)

    def backup():
        path = Path(tempfile.mkdtemp(prefix='physicsprep-backup-'))/'learning-backup.sqlite3'
        service.backup(str(path))
        return str(path)

    def restore(path, confirmed):
        if not confirmed: raise ValueError('恢复会替换当前学习数据库，请勾选确认并先备份。')
        if not path: raise ValueError('请选择备份文件。')
        service.restore(path)
        return '已恢复数据库，请刷新学习总览；如正在答题，请重新继续上次学习。'

    def plan():
        return plan_markdown(service)

    runtime_settings = [settings]

    def client():
        if runtime_settings[0] is not None:
            from physics_prep.llm.client import create_client
            return create_client(runtime_settings[0])
        return llm_factory()

    def ask(qid, feedback, prompt, full):
        if not prompt.strip():
            raise ValueError('请输入你的问题。')
        if llm_factory is None:
            return '当前 AI 客户端尚未就绪；固定题库与判分仍可使用。'
        # 作答前只给提示；提交过或用户明确要求时才允许完整解析。
        after_submit = bool(feedback)
        system = tutor_system(after_submit=after_submit, full_solution=bool(full))
        result = client().ask(prompt, system=system)
        text = result.get('text', '')
        if result.get('mode') == 'mock' and not result.get('error'):
            text += '\n\n> 当前为本地 Mock 教师（非模型推理）。配置 `.env` 后可切换为在线 GenAI。'
        elif result.get('error'):
            text += f"\n\n> 在线调用未成功（{result['error']}），以上为离线引导内容。"
        return text

    def connection():
        if llm_factory is None:
            return 'AI 客户端尚未就绪。'
        return connection_report(client())

    def tutor_chat(session_id, question_id, prompt, full):
        if not session_id or not question_id:
            raise ValueError('请先开始或继续学习。')
        service.tutor(session_id, question_id, prompt, client() if llm_factory else None, full)
        transcript = '\n\n---\n\n'.join('**学生：** '+r['student']+'\n\n**教师：** '+r['teacher']
            for r in service.tutor_history(session_id))
        from sqlalchemy import select
        from ..database.models import Attempt
        with service.factory() as s:
            row = service._session(s, session_id)
            submitted = not row.current_snapshot
            last = s.scalar(select(Attempt).where(Attempt.session_id == session_id).order_by(Attempt.id.desc()))
        summary, detail = feedback_text(last.feedback) if submitted and last else ('','')
        return transcript, gr.update(interactive=not submitted), gr.update(interactive=True), summary, detail

    def restore_chat(session_id):
        return '\n\n---\n\n'.join('**学生：** '+r['student']+'\n\n**教师：** '+r['teacher']
            for r in service.tutor_history(session_id)) if session_id else ''

    def foundation(model):
        topic = 'PHY-MECH-DYN-001' if model == 'newton' else 'PHY-QM-SPIN-001'
        q = service.generate_practice(model, topic)
        return redo(q)

    def route_start(mode, subject, chapter):
        sid = service.start_route(mode, subject, chapter)
        return render_question(service.next(sid), sid)

    def configure(base_url, model, timeout, retries, mock_mode):
        if runtime_settings[0] is None:
            raise ValueError('配置对象尚未就绪。')
        runtime_settings[0] = runtime_settings[0].with_parameters(
            base_url, model, int(timeout), int(retries), mock_mode)
        active = client() if llm_factory else None
        return (f'已应用本次运行配置。\n\n{mode_summary(runtime_settings[0], active)}\n\n'
                '密钥始终只从本地环境变量 / `.env` 读取，界面不接收也不显示完整密钥；'
                '重启后以 `.env` 为准。')

    theme = gr.themes.Soft(primary_hue='indigo', neutral_hue='slate')
    with gr.Blocks(title='PhysicsPrep · 物理考研', theme=theme, css=CSS) as app:
        sid = gr.State(None)
        qid = gr.State(None)
        token = gr.State(None)
        feedback_state = gr.State('')
        gr.HTML('<div class="hero"><h1>PhysicsPrep · 物理考研</h1><p>点击开始刷题，让系统选题；不会就提示，错了就补弱，下次继续。</p></div>')
        with gr.Tabs() as tabs:
            from .practice import mount_practice
            mount_practice(service,client if llm_factory else None)
            with gr.Tab('学习总览', id='dashboard'):
                stats = gr.HTML()
                with gr.Row():
                    with gr.Column(scale=2): activity = gr.Plot()
                    with gr.Column(scale=1): suggestions = gr.Markdown()
                with gr.Row():
                    refresh = gr.Button('刷新学习总览')
                    continue_btn = gr.Button('继续上次学习',variant='primary')
            with gr.Tab('开始诊断', id='quiz'):
                with gr.Row():
                    subject = gr.Dropdown(SUBJECTS,value='',label='科目',scale=1,elem_id='subject-select')
                    chapter = gr.Dropdown(topics_choices(),value='',label='知识点 / 章节',scale=2,elem_id='chapter-select')
                    start_btn = gr.Button('开始诊断',variant='primary',scale=1,elem_id='start-btn')
                with gr.Row():
                    route_mode = gr.Dropdown(['从零开始','快速诊断','指定章节','专项补弱','到期复习'],value='快速诊断',label='学习路线')
                    route_btn = gr.Button('开始这条学习路线')
                with gr.Row():
                    foundation_model = gr.Dropdown([('从牛顿第二定律开始','newton'),('从Born概率开始','born')],value='newton',label='零基础练习（本地机器校验）')
                    foundation_btn = gr.Button('从基础开始')
                metadata = gr.Markdown('选择科目或知识点后点击「开始诊断」。未知掌握度需要多次、不同难度的作答证据才能更新。',elem_id='quiz-meta')
                stem = gr.Markdown('### 准备好开始了吗？\n每道题先独立思考；遇到困难可以查看提示。',latex_delimiters=LATEX,elem_id='question-card')
                radio = gr.Radio([],label='请选择一个选项',visible=False,elem_id='quiz-options')
                multiple = gr.CheckboxGroup([],label='请选择全部正确选项',visible=False)
                answer = gr.Textbox(label='你的计算结果 / 推导',placeholder='例如 sqrt(2*g*h)；允许受控数学表达式，乘号请显式写出。',lines=3,visible=False)
                with gr.Row():
                    submit_btn = gr.Button('提交答案',variant='primary',interactive=False)
                    hint_btn = gr.Button('给我一个提示',interactive=False)
                    solution_btn = gr.Button('查看解析')
                    next_btn = gr.Button('下一题',interactive=False,variant='primary')
                hint = gr.Markdown(latex_delimiters=LATEX)
                gr.Markdown('<span class="status-pill">作答反馈</span>',elem_id='feedback-title')
                feedback = gr.Markdown(latex_delimiters=LATEX,elem_id='feedback-card')
                solution = gr.Markdown(latex_delimiters=LATEX,elem_id='solution-card')
                with gr.Row():
                    mark_btn = gr.Button('标记本题')
                    report_btn = gr.Button('查看本轮诊断报告')
                mark_status = gr.Markdown()
                report = gr.Markdown()
                with gr.Accordion('与私人教师连续学习',open=True):
                    ai_prompt = gr.Textbox(label='想问什么？',placeholder='这个模型为什么适用？请解释推导第二步。',elem_id='ai-prompt')
                    full_solution = gr.Checkbox(label='我主动请求完整解析',value=False,elem_id='full-solution')
                    ai_btn = gr.Button('向 AI 提问',elem_id='ai-btn')
                    ai_response = gr.Markdown(latex_delimiters=LATEX,elem_id='ai-response')
                    legacy_ai = gr.Button('legacy', visible=False)
            with gr.Tab('知识树', id='tree'):
                gr.Markdown('### 知识结构与掌握证据\n未知表示尚未积累足够作答证据。依赖关系用于补救推荐，不代表官方大纲版本。')
                tree_outline = gr.Markdown()
                tree = gr.Dataframe(headers=['稳定 ID','知识点','父节点','前置知识','掌握度'],datatype=['str']*5,interactive=False,wrap=True,elem_id='tree-table')
                with gr.Row():
                    tree_topic = gr.Dropdown(topics_choices(),value='',label='选择考点')
                    topic_practice = gr.Button('练习这个考点',variant='primary')
                    tree_refresh = gr.Button('刷新知识树')
                with gr.Accordion('知识树编辑',open=False):
                    topic_json = gr.Code(language='json',label='知识点 JSON',value=topic_json_template())
                    with gr.Row():
                        topic_save = gr.Button('保存知识点')
                        topic_delete = gr.Button('删除所选知识点')
                    topic_message = gr.Markdown()
                    with gr.Row():
                        topics_file = gr.File(label='导入知识树 JSON',file_types=['.json'],type='filepath')
                        topics_import = gr.Button('校验并导入知识树')
                        topics_export = gr.Button('导出知识树')
                        topics_download = gr.File(label='知识树下载')
            with gr.Tab('错题与复习', id='wrong'):
                with gr.Row():
                    wrong_topic = gr.Dropdown(topics_choices(),value='',label='按考点筛选错题')
                    wrong_refresh = gr.Button('刷新错题与计划')
                    wrong_practice = gr.Button('针对该考点练习',variant='primary')
                wrong_notice = gr.Markdown()
                wrong = gr.Dataframe(headers=['题目 ID','作答时间','原题','你的答案','结果','标准答案','解析'],datatype=['str']*7,interactive=False,wrap=True,elem_id='wrong-table')
                with gr.Row():
                    redo_id = gr.Textbox(label='精确重做题目 ID',placeholder='从错题表复制题目 ID；保留历次记录以供比较。')
                    redo_btn = gr.Button('重新练习这道题',variant='primary')
                history_btn = gr.Button('对比这道题的历次作答')
                history_view_md = gr.Markdown()
                review_plan = gr.Markdown()
            with gr.Tab('题库管理', id='bank'):
                gr.Markdown('### 内容管理\n管理页包含答案，建议在结束诊断后使用。AI 生成题默认未审核；冻结真题不自动导入。')
                with gr.Row():
                    filter_subject = gr.Dropdown(SUBJECTS,value='',label='科目')
                    filter_topic = gr.Dropdown(topics_choices(),value='',label='考点')
                    filter_difficulty = gr.Dropdown(['','1','2','3','4','5'],value='',label='难度')
                    search = gr.Textbox(label='题目搜索')
                    search_btn = gr.Button('搜索')
                question_table = gr.Dataframe(headers=['ID','科目','考点','难度','题型','来源','审核','题面'],datatype=['str']*8,interactive=False,wrap=True)
                with gr.Accordion('创建 / 编辑题目',open=False):
                    edit_id = gr.Textbox(label='读取题目 ID')
                    load_btn = gr.Button('读取内容')
                    editor = gr.Code(language='json',label='题目完整 JSON',lines=15)
                    with gr.Row():
                        save_btn = gr.Button('保存题目',variant='primary')
                        delete_btn = gr.Button('删除该题')
                    edit_message = gr.Markdown()
                    review_evidence = gr.Textbox(label='审核依据',placeholder='记录独立校验方法、明确审核人或核验来源；不能只写“正确”。')
                    with gr.Row():
                        review_verified = gr.Checkbox(label='将当前题标记为已审核（我已完成校验）',value=False)
                        review_btn = gr.Button('记录明确审核结果')
                with gr.Row():
                    import_file = gr.File(label='导入 JSON / CSV',file_types=['.json','.csv'],type='filepath')
                    with gr.Column():
                        import_btn = gr.Button('校验并导入')
                        export_type = gr.Radio(['JSON','CSV'],value='JSON',label='导出格式')
                        export_btn = gr.Button('导出全部题目')
                        export_file = gr.File(label='题库下载')
                import_status = gr.Markdown()
            with gr.Tab('设置与备份', id='settings'):
                gr.Markdown('### 本地运行与 AI 连接\n默认只监听本机（127.0.0.1），不开启公开分享链接。密钥只从本地 `.env` / 环境变量读取，界面不显示完整密钥。修改 `.env` 后需重启生效；没有密钥时自动使用 Mock 模式，全部核心功能可用。')
                mode_md = gr.Markdown(mode_summary(settings, client() if llm_factory else None))
                gr.Markdown('连续教师会发送当前题面、关联知识点及本会话最近六轮对话，以便接续讲解；不发送整份教材、密钥或全部学习数据库。离线模式不发送网络请求。')
                with gr.Row():
                    base_url = gr.Textbox(label='GenAI API Address',value=getattr(settings,'base_url',''))
                    model = gr.Textbox(label='模型 ID',value=getattr(settings,'model',''))
                with gr.Row():
                    timeout = gr.Number(label='超时（秒）',value=getattr(settings,'timeout',60),minimum=1,maximum=180,precision=0)
                    retries = gr.Number(label='重试次数',value=getattr(settings,'max_retries',2),minimum=0,maximum=5,precision=0)
                    mock_mode = gr.Checkbox(label='强制使用 Mock',value=getattr(settings,'effective_mock',True))
                configure_btn = gr.Button('应用本次运行配置')
                configure_status = gr.Markdown()
                gr.Markdown(f"**密钥状态：** {mask_key(getattr(settings,'api_key',''))}（完整密钥永不显示，也不写入日志）")
                connection_btn = gr.Button('测试模型连接',variant='primary')
                connection_result = gr.Markdown(elem_id='connection-result')
                gr.Markdown(backup_help(service.path))
                backup_btn = gr.Button('备份当前数据库')
                backup_file = gr.File(label='下载 SQLite 备份')
                restore_file = gr.File(label='上传 SQLite 备份',file_types=['.sqlite3','.db','.sqlite'],type='filepath')
                confirm_restore = gr.Checkbox(label='我确认用备份替换当前数据库（已备份当前数据）',value=False)
                restore_btn = gr.Button('恢复备份')
                restore_status = gr.Markdown()
                gr.Markdown('### 大纲版本归档\n导入你已核对来源的大纲。版本按文件 SHA256 留存；系统不会将未经核对的文件认定为某年度官方大纲。')
                syllabus_file = gr.File(label='大纲 PDF / JSON / TXT / CSV',file_types=['.pdf','.json','.txt','.csv'],type='filepath')
                with gr.Row():
                    syllabus_label = gr.Textbox(label='版本标签',placeholder='例如：本地普物大纲（待确认年份）')
                    syllabus_subject = gr.Dropdown(SUBJECTS,value='',label='大纲科目')
                    syllabus_import = gr.Button('归档大纲')
                syllabus_versions = gr.JSON(label='已有大纲版本')
                syllabus_table = gr.Markdown()

        outputs = [sid,qid,token,metadata,stem,radio,multiple,answer,hint,feedback,submit_btn,hint_btn,next_btn]
        # Reset stale feedback, solution and teacher output on every question transition.
        def clear_explanation(): return '', '', '', '', '', '', False
        clear_outputs=[solution,feedback_state,ai_response,report,mark_status,ai_prompt,full_solution]
        start_btn.click(safe(start),[subject,chapter],outputs).then(clear_explanation,outputs=clear_outputs)
        foundation_btn.click(safe(foundation,'foundation'),[foundation_model],outputs).then(clear_explanation,outputs=clear_outputs)
        route_btn.click(safe(route_start,'route_start'),[route_mode,subject,chapter],outputs).then(clear_explanation,outputs=clear_outputs)
        continue_btn.click(safe(resume),outputs=outputs).then(lambda:gr.update(selected='quiz'),outputs=tabs).then(clear_explanation,outputs=clear_outputs).then(safe(restore_chat,'restore_tutor_chat'),[sid],[ai_response])
        next_btn.click(safe(advance),[sid],outputs).then(clear_explanation,outputs=clear_outputs)
        submit_btn.click(safe(submit),[sid,qid,token,radio,multiple,answer],[feedback,feedback_state,submit_btn,next_btn],concurrency_limit=1)
        hint_btn.click(safe(lambda q,s:service.hint(q,s),'hint'),[qid,sid],[hint])
        solution_btn.click(safe(reveal,'reveal'),[qid,feedback_state],[solution])
        report_btn.click(safe(lambda s: '### 诊断报告\n```json\n'+json.dumps(service.report(s),ensure_ascii=False,indent=2)+'\n```' if s else '请先开始诊断。','report'),[sid],[report])
        mark_btn.click(safe(lambda q:service.mark_question(q) if hasattr(service,'mark_question') else '题目标记暂不可用。','mark_question'),[qid],[mark_status])
        ai_btn.click(safe(tutor_chat,'tutor_chat'),[sid,qid,ai_prompt,full_solution],[ai_response,submit_btn,next_btn,feedback,feedback_state])
        # Keep the legacy API available for existing integrations.
        legacy_ai.click(safe(ask,'ask'),[qid,feedback_state,ai_prompt,full_solution],[ai_response])
        refresh.click(safe(lambda:dashboard_view(service.dashboard()),'refresh_dashboard'),outputs=[stats,activity,suggestions])
        tree_refresh.click(safe(lambda:(tree_view(),tree_structure()),'refresh_tree'),outputs=[tree,tree_outline])
        topic_practice.click(safe(lambda t:start('',t),'practice_topic'),[tree_topic],outputs).then(lambda:gr.update(selected='quiz'),outputs=tabs).then(clear_explanation,outputs=clear_outputs)
        wrong_practice.click(safe(lambda t:start('',t),'practice_wrong_topic'),[wrong_topic],outputs).then(lambda:gr.update(selected='quiz'),outputs=tabs).then(clear_explanation,outputs=clear_outputs)
        redo_btn.click(safe(redo,'redo'),[redo_id],outputs).then(lambda:gr.update(selected='quiz'),outputs=tabs).then(clear_explanation,outputs=clear_outputs)
        wrong_refresh.click(safe(lambda t:(wrong_view(t),wrong_summary(service,t or None)),'refresh_wrong'),[wrong_topic],[wrong,wrong_notice]).then(safe(plan,'plan'),outputs=[review_plan])
        history_btn.click(safe(history_view,'attempt_history'),[redo_id],[history_view_md])
        topic_save.click(safe(save_topic,'save_topic'),[topic_json],[topic_message,tree]).then(safe(tree_structure,'tree_structure'),outputs=tree_outline)
        topic_delete.click(safe(lambda t:(service.delete_topic(t),'已删除知识点。')[1],'delete_topic'),[tree_topic],[topic_message]).then(safe(tree_view,'tree_view'),outputs=tree).then(safe(tree_structure,'tree_structure'),outputs=tree_outline)
        topics_import.click(safe(lambda p:'已导入知识点数量：'+str(service.import_topics(p)),'import_topics'),[topics_file],[topic_message]).then(safe(tree_view,'tree_view'),outputs=tree).then(safe(tree_structure,'tree_structure'),outputs=tree_outline)
        topics_export.click(safe(export_topics,'export_topics'),outputs=topics_download)
        search_btn.click(safe(question_list,'search_questions'),[filter_subject,filter_topic,filter_difficulty,search],[question_table])
        load_btn.click(safe(load_question,'load_question'),[edit_id],[editor])
        save_btn.click(safe(save_question,'save_question'),[editor],[edit_message])
        delete_btn.click(safe(lambda q:(service.delete_question(q),'已删除题目；历史记录保留快照。')[1],'delete_question'),[edit_id],[edit_message])
        review_btn.click(safe(lambda q,v,e:'已记录审核：'+str(service.review_question(q,v,e)),'review_question'),[edit_id,review_verified,review_evidence],[edit_message])
        import_btn.click(safe(lambda p:str(service.import_questions(p)),'import_questions'),[import_file],[import_status])
        export_btn.click(safe(export,'export_questions'),[export_type],[export_file])
        connection_btn.click(safe(connection,'connection'),outputs=connection_result)
        configure_btn.click(safe(configure,'configure'),[base_url,model,timeout,retries,mock_mode],[configure_status])
        backup_btn.click(safe(backup,'backup'),outputs=backup_file)
        restore_btn.click(safe(restore,'restore'),[restore_file,confirm_restore],[restore_status])
        syllabus_import.click(safe(lambda p,l,s:syllabus.import_version(p,l,s),'import_syllabus'),[syllabus_file,syllabus_label,syllabus_subject],[syllabus_versions]).then(safe(lambda:syllabus_help(syllabus.list_versions()),'syllabus_table'),outputs=syllabus_table)
        app.load(safe(syllabus.list_versions,'list_syllabus'),outputs=syllabus_versions)
        app.load(safe(lambda:syllabus_help(syllabus.list_versions()),'syllabus_table'),outputs=syllabus_table)
        app.load(safe(lambda:dashboard_view(service.dashboard()),'refresh_dashboard'),outputs=[stats,activity,suggestions])
        app.load(safe(tree_view,'tree_view'),outputs=tree)
        app.load(safe(tree_structure,'tree_structure'),outputs=tree_outline)
        app.load(safe(lambda:wrong_view(''),'refresh_wrong'),outputs=wrong)
        app.load(safe(lambda:wrong_summary(service,None),'wrong_summary'),outputs=wrong_notice)
        app.load(safe(plan,'plan'),outputs=review_plan)
        app.load(safe(lambda:question_list('','','',''),'search_questions'),outputs=question_table)
    return app
