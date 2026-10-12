from physics_prep.diagnosis.selector import select_question

def q(qid,topic,difficulty):
    return {'id':qid,'subject':'mechanics','topic_ids':[topic],'difficulty':difficulty,
        'verified':True,'source_type':'original','question_type':'numeric'}

def test_level_fit_changes_with_evidence():
    pool=[q('basic','t',1),q('advanced','t',3)]
    assert select_question(pool,[],{})['id']=='basic'
    assert select_question(pool,[],{'t':{'estimate':.8}})['id']=='advanced'

def test_prerequisite_readiness_prevents_premature_combination():
    pool=[q('pre','p',1),q('combined','t',1)]
    assert select_question(pool,[],{}, {'t':['p']})['id']=='pre'

def test_due_changes_equal_level_priority_and_reason():
    pool=[q('a','t',1),q('b','u',1)]
    chosen=select_question(pool,[],{},due={'t'})
    assert chosen['id']=='a' and '到期' in chosen['recommendation_reason']

def test_consecutive_errors_move_to_prerequisite():
    pool=[q('pre','p',1),q('combo','t',3),q('another','u',3)]
    history=[{'question_id':'combo','topic_ids':['t'],'status':'incorrect'}]*3
    chosen=select_question(pool,history,{'t':{'estimate':.1}}, {'t':['p']})
    assert chosen['id']=='pre'
