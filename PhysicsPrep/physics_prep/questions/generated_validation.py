"""Independent algebra/physical checks for the explicitly supported model families."""
import sympy as sp
from fractions import Fraction


def dimensional_check(model,variant,unit):
    # Exponents of (mass, length, time); radians and probabilities are dimensionless.
    mass=(1,0,0); length=(0,1,0); time=(0,0,1); force=(1,1,-2)
    moment=(1,2,-2); inertia=(1,2,0)
    add=lambda a,b: tuple(x+y for x,y in zip(a,b))
    sub=lambda a,b: tuple(x-y for x,y in zip(a,b))
    dims={'newton':sub(force,mass),'born':(0,0,0),'torque':add(force,length),
        'angular_acceleration':add(sub(moment,inertia),time) if variant%2 else sub(moment,inertia),
        'normalization':(0,Fraction(-1,2),0),'rope_no_slip':add(length,(0,0,-2)),
        'pulley':sub(add(mass,(0,1,-2)),mass)}
    units={'m/s²':(0,1,-2),'dimensionless':(0,0,0),'N·m':(1,2,-2),
        'rad/s²':(0,0,-2),'rad/s':(0,0,-1),'m^(-1/2)':(0,Fraction(-1,2),0)}
    denominator_ok=sub(inertia,add(length,length))==mass
    return dims.get(model)==units.get(unit) and (model!='pulley' or denominator_ok)


def validate_generated(record):
    checks={}; errors=[]
    try:
        gen=record['generation']; model=gen['model']; p=gen['parameters']
        # Numeric parameters only. No eval or arbitrary model expressions.
        if any(type(v) is not int or not 0 < v <= 100 for v in p.values()):
            raise ValueError('invalid parameters')
        if model=='newton':
            expected=sp.Rational(p['force'],p['mass']); dimension='N/kg=m/s²'
            checks['positive_mass']=p['mass']>0
        elif model=='born':
            expected=sp.Rational(p['numerator'],p['denominator']); dimension='dimensionless'
            checks['probability_range']=0<expected<1
            checks['normalized']=expected+sp.Rational(p['denominator']-p['numerator'],p['denominator'])==1
        elif model=='torque':
            expected=sp.Integer(p['radius'])*p['force']; dimension='N·m'
            checks['positive_lever_arm']=p['radius']>0
        elif model=='angular_acceleration':
            expected=sp.Rational(p['torque'],p['inertia'])
            dimension='N·m/(kg·m²)=s^(-2)' if gen['variant']%2==0 else 's^(-2)×s=s^(-1)'
            checks['positive_inertia']=p['inertia']>0
        elif model=='normalization':
            expected=1/sp.sqrt(p['length']); dimension='m^(-1/2)'
            x=sp.Symbol('x',real=True)
            checks['normalization_integral']=sp.integrate(expected**2,(x,0,p['length']))==1
        elif model=='rope_no_slip':
            radius=sp.Rational(p['radius_dm'],10)
            t=sp.Symbol('t',real=True)
            expected=sp.diff(radius*p['alpha']*t,t); dimension='m×s^(-2)=m/s²'
            checks['radius_positive']=radius>0
        elif model=='pulley':
            m=sp.Integer(p['mass']); inertia=sp.Rational(p['inertia_scaled'],100)
            radius=sp.Rational(p['radius_dm'],10); g=sp.Integer(p['gravity'])
            a,tension=sp.symbols('a tension',real=True)
            solved=sp.solve([m*g-tension-m*a,tension*radius-inertia*a/radius],(a,tension))
            expected=solved[a]; dimension='(kg×m/s²)/(kg+kg)=m/s²'
            h=sp.Symbol('h',positive=True)
            energy_v_sq=2*m*g*h/(m+inertia/radius**2)
            checks['independent_energy_path']=sp.simplify(sp.diff(energy_v_sq,h)/2-expected)==0
            checks['acceleration_range']=0<expected<g
            checks['tension_range']=0<solved[tension]<m*g
            arbitrary_I=sp.Symbol('I',positive=True)
            formula=m*g/(m+arbitrary_I/radius**2)
            checks['zero_inertia_limit']=sp.limit(formula,arbitrary_I,0)==g
            checks['large_inertia_limit']=sp.limit(formula,arbitrary_I,sp.oo)==0
        else:
            return {'status':'needs_review','passed':False,'checks':{},'errors':['unsupported_model']}
        # Accept only the canonical answer syntax, then compare independent expected result.
        from .generation import canonical
        reference=canonical(model,gen['variant'])
        checks['canonical_subject']=record.get('subject')==reference['subject']
        checks['canonical_type']=record.get('question_type')==('symbolic' if model=='normalization' else 'numeric')
        checks['canonical_difficulty']=record.get('difficulty')==(3 if model=='pulley' else 1)
        checks['canonical_parameters']=p==reference['parameters']
        checks['canonical_statement']=record['stem']==reference['stem']
        checks['canonical_solution']=record['solution']==reference['solution']
        checks['canonical_hints']=record.get('hints')=={str(i+1):v for i,v in enumerate(reference['hints'])}
        checks['canonical_conditions']=record.get('physical_conditions')==reference['conditions']
        checks['canonical_unit']=record.get('answer_unit')==reference['unit']
        checks['dimensional_consistency']=dimensional_check(model,gen['variant'],record.get('answer_unit'))
        answer=record['correct_answer']
        checks['canonical_answer_syntax']=isinstance(answer,str) and answer==reference['answer']
        if checks['canonical_answer_syntax']:
            actual=sp.sympify(answer,locals={'sqrt':sp.sqrt})
            checks['independent_answer']=sp.simplify(actual-expected)==0
        else:
            checks['independent_answer']=False
        checks['dimension']=dimension
        checks={key: value if isinstance(value,str) else bool(value) for key,value in checks.items()}
        errors=[key for key,value in checks.items() if value is False]
    except (KeyError,ValueError,TypeError,ZeroDivisionError):
        errors=['invalid_generation_record']
    return {'status':'rejected' if errors else 'machine_validated','passed':not errors,'checks':checks,'errors':errors,
            'scope':'Canonical elementary model only; no claim about arbitrary physical derivations.'}

