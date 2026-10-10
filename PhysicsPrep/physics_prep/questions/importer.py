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
    review = record.get('review') or {}
    statement_ok = review.get('statement_status') == 'verified'
    solution_ok = review.get('solution_status') in ('checked', 'verified')
    if not (statement_ok and solution_ok):
        raise ValueError(f"{record.get('id', '<unknown>')}: writing record is not practice-ready")
    solution = record.get('solution') or {}
    topics = record.get('syllabus_topics') or []
    if not topics:
        raise ValueError(f"{record.get('id', '<unknown>')}: missing syllabus_topics")
    return {
        'id': record['id'], 'subject': record.get('subject', 'mechanics'),
        'topic_ids': topics, 'difficulty': int(record.get('difficulty', 2)),
        'question_type': record.get('question_type', 'short_answer'),
        'stem': record.get('statement', ''), 'options': record.get('options', []),
        'correct_answer': solution.get('final_answer', ''),
        'solution': '\n'.join(solution.get('steps') or []) or solution.get('final_answer', ''),
        'source_type': 'textbook', 'source_reference': record.get('sources', []),
        'verified': True, 'content_status': 'practice_ready',
        'content_priority': int(record.get('content_priority', 0)),
        'writing_record': record,
    }


def import_writing_record(repository: Repository, path):
    record = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return repository.save_questions([adapt_writing_record(record)])
