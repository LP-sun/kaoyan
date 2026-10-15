import pytest
from pathlib import Path
from sqlalchemy import select
from physics_prep.services.learning import LearningService
from physics_prep.database.models import MasteryRecord
from physics_prep.diagnosis.math_grader import grade, controlled_parse, InputError


def test_pressure_accepts_implicit_product_but_does_not_rename_particle_count():
    opts={'allowed_symbols':['n','R','T','V'],'positive_symbols':['n','R','T','V']}
    assert grade('nRT/V','n*R*T/V','symbolic',opts)['status']=='correct'
    result=grade('NRT/V','n*R*T/V','symbolic',opts)
    assert result['status']=='uncertain'
    assert '大小写' in result['explanation'] and 'nRT' in result['explanation']
    assert grade('nRT*V','n*R*T/V','symbolic',opts)['status']=='incorrect'


def test_ambiguous_implicit_product_is_not_guessed():
    with pytest.raises(InputError):
        controlled_parse('abc',{'names':['a','bc','ab','c']})
    assert str(controlled_parse('ab',{'names':['a','b','ab']}))=='ab'


def test_pressure_actual_submit_path_preserves_ambiguous_evidence(tmp_path):
    service=LearningService(tmp_path/'pressure.sqlite3',Path(__file__).parents[1]/'data')
    sid=service.start(question_id='PHY-000017')
    result=service.submit(sid,'PHY-000017','nRT/V','pressure-correct')
    assert result['status']=='correct'
    other=service.start(question_id='PHY-000017')
    with service.factory() as s:
        before=s.scalar(select(MasteryRecord).where(MasteryRecord.topic_id=='PHY-THERM-GAS-001')).attempts
    result=service.submit(other,'PHY-000017','NRT/V','pressure-ambiguous')
    assert result['status']=='uncertain' and '大小写' in result['explanation']
    with service.factory() as s:
        assert s.scalar(select(MasteryRecord).where(MasteryRecord.topic_id=='PHY-THERM-GAS-001')).attempts==before


@pytest.mark.parametrize('text',['__import__("os")','a.__class__','[a for a in b]','2**100000','nnnnnnnnnnnnnnnnnnnnnn'])
def test_implicit_products_keep_parser_limits(text):
    assert grade(text,'n','symbolic',{'allowed_symbols':['n','a','b']})['status']=='uncertain'
