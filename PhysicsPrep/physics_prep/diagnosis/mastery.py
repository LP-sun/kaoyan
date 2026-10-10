from datetime import timedelta
from ..clock import naive_utcnow

def update_mastery(record, correct, difficulty, now=None):
    """Beta(2,2) 收缩 + 近期加权；这是启发式估计，不是已校准的 BKT / IRT 测量。"""
    now=now or naive_utcnow()
    record.attempts=(record.attempts or 0)+1
    record.correct=(record.correct or 0)+int(correct)
    recent=list(record.recent or [])[-7:]+[{'correct':bool(correct),'difficulty':difficulty}]
    weighted=sum((1 if r['correct'] else 0)*(1+(r['difficulty']-1)*.12)*(i+1) for i,r in enumerate(recent))
    denominator=sum((1+(r['difficulty']-1)*.12)*(i+1) for i,r in enumerate(recent))
    history=(record.correct+2)/(record.attempts+4)
    record.estimate=round(min(.95,max(.05,.7*history+.3*weighted/denominator)),4)
    record.recent=recent; record.last_practiced=now
    streak=0
    for r in reversed(recent):
        if not r['correct']: break
        streak+=1
    interval=1 if not correct else (3 if streak<2 else 7 if streak<4 else 14)
    return interval, now+timedelta(days=interval)
