"""Executable validation for two simple physical model families."""
from fractions import Fraction
import hashlib
import sympy as sp


def generate(model, topic_id, variant=0):
    n = int(variant)
    if not 0 <= n <= 1000:
        raise ValueError('变式编号必须在0至1000之间。')
    if model == 'newton':
        mass, force = 2+n%5, 6+n%11
        answer = str(Fraction(force, mass))
        stem = f'质量{mass} kg的物体在惯性系中受到水平合力{force} N，求加速度大小（m/s²）。'
        if n % 2:
            stem = f'在惯性系中，质量{mass} kg的小车受水平合力{force} N。每经过1秒，它的速度增加多少m/s？忽略质量变化。'
        solution = f'惯性系中使用合力F=ma，a=F/m={answer} m/s²。'
        assert sp.Rational(answer)*mass-force == 0 and mass > 0
        subject = 'mechanics'
        hints = {'1':'先区分合力和单个力。哪个定律联系合力与加速度？',
                 '2':'牛顿第二定律为F=ma。需要解出哪个未知量？',
                 '3':'将方程两边除以质量m；检查单位N/kg=m/s²。'}
        checks = {'equation_residual': 0, 'mass_positive': True, 'dimension': 'N/kg=m/s²'}
    elif model == 'born':
        a, b = 1+n%4, 5+n%4
        value = Fraction(a, b)
        answer = str(value)
        stem = f'归一化自旋态为sqrt({a}/{b})|+z> + sqrt({b-a}/{b})|-z>，求测得+z的概率。'
        solution = f'Born规则：概率为振幅的模平方，P(+z)={answer}。'
        assert value+Fraction(b-a,b) == 1 and 0 < value < 1
        subject = 'quantum'
        hints = {'1':'振幅与概率不是同一个量。Born规则如何联系它们？',
                 '2':'对应结果的概率是振幅的模平方。', '3':'将sqrt(...)取模平方，并检查概率和为1。'}
        checks = {'normalization': True, 'probability_range': True, 'dimension': 'dimensionless'}
    else:
        raise ValueError('当前支持newton和born；复杂题不声称自动验证。')
    key = hashlib.sha256(f'{model}:{topic_id}:{n}:v1'.encode()).hexdigest()[:16]
    return {'id':'GEN-'+key, 'subject':subject, 'topic_ids':[topic_id], 'difficulty':1,
        'question_type':'numeric', 'stem':stem, 'correct_answer':answer, 'solution':solution,
        'source_type':'ai_generated', 'verified':False, 'human_verified':False,
        'machine_validated':True, 'content_status':'practice_ready',
        'generation':{'model':model,'variant':n,'version':1}, 'validation':checks,
        'hints':hints, 'hint':hints['1'], 'estimated_minutes':2,
        'time_source':'template_estimate', 'difficulty_source':'template_design'}
