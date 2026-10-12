"""Single quality gate shared by scheduling and submission."""
import json
from functools import lru_cache


@lru_cache(maxsize=512)
def _current_machine_check(serialized):
    from .generated_validation import validate_generated
    try:
        return validate_generated(json.loads(serialized))['passed']
    except Exception:
        return False


def is_practice_eligible(q):
    basic=bool(q and (q.get('verified') or q.get('machine_validated')) and
        q.get('content_status','practice_ready') == 'practice_ready' and
        not q.get('frozen') and q.get('source_type') != 'official_exam' and not q.get('reported_issue'))
    if not basic or q.get('verified'):
        return basic
    return _current_machine_check(json.dumps(q,ensure_ascii=False,sort_keys=True))
