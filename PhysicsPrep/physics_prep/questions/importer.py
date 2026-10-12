from pathlib import Path
import json
from .repository import Repository

def import_questions(repository: Repository, path):
    return repository.import_questions(path)


def adapt_writing_record(record: dict) -> dict:
    """Map one 题库写作 record to the stable PhysicsPrep question shape.

    Drafts are intentionally rejected: they remain in the writing workspace
    until both statement and solution have been checked by a human.
    """
    if record.get('frozen') or record.get('source_type')=='official_exam':
        raise ValueError('冻结或模拟真题不能通过教材接口进入普通练习池。')
    review = record.get('review') or {}
    statement_ok = review.get('statement_status') == 'verified'
    solution_ok = review.get('solution_status') in ('checked', 'verified')
    if not (statement_ok and solution_ok):
        raise ValueError(f"{record.get('id', '<unknown>')}: writing record is not practice-ready")
    if review.get('reviewer_kind')!='human' or not all(str(review.get(k) or '').strip()
            for k in ('statement_evidence','solution_evidence')):
        raise ValueError('教材写作记录需要明确的人工复核身份与题面、解析证据；机器检查不能冒称人工审核。')
    if not record.get('subject') or record.get('difficulty') is None or not record.get('difficulty_source'):
        raise ValueError('请显式提供科目、难度及标注来源，不能默认猜测。')
    solution = record.get('solution') or {}
    if solution.get('final_answer') in (None,'',[]) or not solution.get('steps') or not solution.get('checks'):
        raise ValueError('教材练习题必须有非空标准答案、解析步骤与检查依据。')
    topics = record.get('syllabus_topics') or []
    if not topics:
        raise ValueError(f"{record.get('id', '<unknown>')}: missing syllabus_topics")
    return {
        'id': record['id'], 'subject': record['subject'],
        'topic_ids': topics, 'difficulty': int(record['difficulty']),
        'question_type': record.get('question_type', 'short_answer'),
        'stem': record.get('statement', ''), 'options': record.get('options', []),
        'correct_answer': solution.get('final_answer', ''),
        'solution': '\n'.join(step if isinstance(step,str) else json.dumps(step,ensure_ascii=False)
            for step in solution['steps']),
        'source_type': 'textbook', 'source_reference': record.get('sources', []),
        'verified': True, 'content_status': 'practice_ready',
        'human_verified': True, 'difficulty_source':record['difficulty_source'],
        'content_priority': int(record.get('content_priority', 0)),
        'writing_record': record,
    }


def import_writing_record(repository: Repository, path):
    record = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return repository.save_questions([adapt_writing_record(record)])
