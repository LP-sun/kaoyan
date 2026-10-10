"""Trusted seed compatibility plus meaningful input-boundary checks."""
import json
from pathlib import Path
import pytest
from physics_prep.diagnosis.math_grader import grade

SEEDS=json.loads((Path(__file__).resolve().parents[1]/'data'/'seed_questions.json').read_text(encoding='utf-8'))

@pytest.mark.parametrize('question',[q for q in SEEDS if q['question_type']!='short_answer'],ids=lambda q:q['id'])
def test_all_verified_objective_seeds_grade_their_standard_answers(question):
    result=grade(question['correct_answer'],question['correct_answer'],question['question_type'],question)
    assert result['status']=='correct', (question['id'],result)

def test_short_answer_is_not_claimed_to_be_machine_verified_semantics():
    q=next(q for q in SEEDS if q['question_type']=='short_answer')
    assert grade(q['correct_answer'],q['correct_answer'],q['question_type'],q)['status']=='uncertain'
    assert q['verification']['human_review'] is False

def test_rolling_alternative_form_and_positive_domain():
    q=next(q for q in SEEDS if q['id']=='PHY-000006')
    # m is an extra parameter expressly configured for this equivalent form.
    options={**q,'allowed_symbols':['M','g','theta'],'positive_symbols':['M','g','theta']}
    assert grade('M*g*sin(theta)/(M+M/2)',q['correct_answer'],'symbolic',options)['status']=='correct'
    assert grade('g*sin(theta)',q['correct_answer'],'symbolic',q)['status']=='incorrect'
    assert grade('sqrt(L**2)/L','1','symbolic',allowed_symbols=['L'],positive_symbols=['L'])['status']=='correct'

@pytest.mark.parametrize('attack',[
    '__import__("os").system("echo unsafe")',
    '(1).__class__.__mro__',
    '[x for x in [1]]',
    '(lambda:1)()',
    '2**100000',
    '1/0',
    'sqrt(',
    'x'*301,
])
def test_untrusted_expression_syntax_returns_uncertain(attack):
    assert grade(attack,'1','numeric',grading_timeout=2)['status']=='uncertain'

def test_zero_numeric_answer_and_complex_constant():
    assert grade(0,'0','numeric')['status']=='correct'
    assert grade('sqrt(-1)*hbar','I*hbar','symbolic',allowed_symbols=['hbar'],positive_symbols=['hbar'])['status']=='correct'

def test_generated_content_is_not_mislabeled_as_textbook_or_official():
    assert len(SEEDS)==30
    assert all(q['source_type']=='original' and q['source_reference'] is None for q in SEEDS)
    assert all(q['verification']['human_review'] is False for q in SEEDS)
    assert all(q['verification']['check'] for q in SEEDS)
