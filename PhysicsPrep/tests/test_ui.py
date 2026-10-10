from physics_prep.ui.quiz import render_question, feedback_text
from physics_prep.ui.dashboard import dashboard_view


def test_public_question_render_has_no_answer_state():
    q = {'id':'q1','stem':'求加速度','question_type':'symbolic','topic_ids':['t'],'difficulty':2,'correct_answer':'SECRET','solution':'SECRET'}
    result = render_question(q,'session')
    assert 'SECRET' not in str(result)
    assert result[0:2] == ('session','q1')
    assert len(result) == 13


def test_switching_question_clears_inputs_and_feedback():
    result = render_question({'id':'q2','stem':'第二题','question_type':'single_choice','options':['A','B']},'s')
    assert result[5]['value'] is None
    assert result[7]['value'] == ''
    assert result[8:10] == ('','')
    assert result[-1]['interactive'] is False


def test_feedback_and_unknown_dashboard():
    text, detail = feedback_text({'status':'uncertain','correct_answer':'x','solution':'推导'})
    assert '人工确认' in text and '推导' in detail
    cards, fig, advice = dashboard_view({'seven_day_accuracy':None})
    assert '尚无记录' in cards
    assert '尚无足够证据' in advice
    assert len(fig.data) == 1
