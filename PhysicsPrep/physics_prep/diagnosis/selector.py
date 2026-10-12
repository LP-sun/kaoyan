from datetime import datetime

# 能被确定性判分器给出 correct/incorrect 的题型（与 math_grader.grade 的分支保持一致）。
# 简答/推导题（short_answer）只能得到 uncertain：不更新掌握度、占用诊断名额，
# 因此自适应诊断不主动派发；仅当候选池里只剩它们时才照常派发，避免无题可做。
# 通过题目 ID 的显式重做不经过本函数，开放题仍然可以主动练习与人工复核。
AUTO_GRADED_TYPES = frozenset({'single_choice', 'multiple_choice', 'numeric', 'symbolic',
                               'numeric_calculation', 'symbolic_expression'})

def select_question(questions, attempts, mastery, prerequisites=None, due=None):
    """Explainable ranking with coverage, remedy, level fit and repetition penalty."""
    prerequisites=prerequisites or {}; due=due or set()
    eligible=[q for q in questions if (q.get('verified') or q.get('machine_validated')) and q.get('source_type')!='official_exam' and not q.get('frozen',False)
              and q.get('content_status', 'practice_ready') == 'practice_ready']
    if not eligible: return None
    gradable=[q for q in eligible if q.get('question_type') in AUTO_GRADED_TYPES]
    if gradable: eligible=gradable
    seen={a['question_id'] for a in attempts}; recent=[a['question_id'] for a in attempts[-3:]]
    unseen=[q for q in eligible if q['id'] not in seen]
    if unseen: eligible=unseen
    else:
        eligible=[q for q in eligible if q['id'] not in recent] or [q for q in eligible if not recent or q['id']!=recent[-1]]
    if not eligible: return None
    last=attempts[-1] if attempts else None
    remedy=set()
    if last and last['status']=='incorrect':
        for t in last['topic_ids']:
            remedy.add(t); remedy.update(prerequisites.get(t,[]))
    last_topics=set(last['topic_ids']) if last else set()
    repeated_topics=set.intersection(*(set(a['topic_ids']) for a in attempts[-3:])) if len(attempts)>=3 else set()
    def score(q):
        scores=[]; reasons=[]
        for t in q['topic_ids']:
            m=mastery.get(t); estimate=m.get('estimate') if m else None
            target=1 if estimate is None else max(1,min(5,round(1+4*estimate)))
            if last and last['status']=='incorrect' and t in remedy: target=max(1,target-1)
            val=5 if estimate is None else 3*(1-estimate)
            if t in due: val+=2; reasons.append('到期复习')
            if t in remedy: val+=4; reasons.append('错误后补救或前置知识')
            if estimate is None: reasons.append('未测试考点')
            if t in repeated_topics: val-=7; reasons.append('控制连续同考点练习')
            val-=abs(q['difficulty']-target)*1.2
            scores.append(val)
        return max(scores), reasons
    result=max(eligible,key=lambda q:(score(q)[0],-q['difficulty'],q['id']))
    return result | {'recommendation_reason':'；'.join(dict.fromkeys(score(result)[1])) or '当前掌握程度与难度匹配'}
