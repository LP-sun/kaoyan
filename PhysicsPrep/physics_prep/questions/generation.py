"""Canonical, bounded physical exercises; model text is never an answer oracle."""
from fractions import Fraction
import hashlib

SUPPORTED_MODELS = ('newton', 'born', 'torque', 'angular_acceleration', 'normalization', 'rope_no_slip', 'pulley')
MODEL_PERIODS = {'newton':55, 'born':4, 'torque':391, 'angular_acceleration':391, 'normalization':97, 'rope_no_slip':33,'pulley':231}


def canonical(model, variant=0):
    if type(variant) is not int or not 0 <= variant <= 1000:
        raise ValueError('variant must be an integer from 0 to 1000')
    n = variant
    if model == 'newton':
        m, f = 2+n%5, 6+n%11
        return dict(subject='mechanics', parameters={'mass':m,'force':f}, answer=str(Fraction(f,m)),
            stem=f'惯性系中，质量 {m} kg 的物体受到恒定水平合力 {f} N，求加速度大小（m/s²）。',
            solution=f'惯性系中 F=ma，a=F/m={Fraction(f,m)} m/s²。',
            hints=['考虑合力与加速度的关系。','使用牛顿第二定律 F=ma。','两边除以质量，检查 N/kg=m/s²。'],conditions=['惯性系','质量恒定'],unit='m/s²')
    if model == 'born':
        a,b=1+n%4,5+n%4
        return dict(subject='quantum', parameters={'numerator':a,'denominator':b},answer=str(Fraction(a,b)),
            stem=f'归一化自旋态为 $\\sqrt{{{a}/{b}}}|+z\\rangle+\\sqrt{{{b-a}/{b}}}|-z\\rangle$，求测得 $+z$ 的概率。',
            solution=f'Born 规则：概率是对应振幅模平方，P(+z)={Fraction(a,b)}。',
            hints=['区分振幅与概率。','概率等于对应振幅的模平方。','将 sqrt(...) 取模平方，并检查概率和为 1。'],conditions=['正交归一基','态已归一化'],unit='dimensionless')
    if model == 'torque':
        r,f=1+n%17,3+n%23
        return dict(subject='mechanics',parameters={'radius':r,'force':f},answer=str(r*f),
            stem=(f'固定转轴到作用点的距离为 {r} m，大小 {f} N 的力沿切向作用，方向使物体逆时针转动。以逆时针为正，求力矩（N·m）。' if n%2==0 else f'力的作用线到固定转轴的垂直距离为 {r} m，力大小为 {f} N，产生逆时针转动趋势。取逆时针为正，求该力对转轴的力矩（N·m）。'),
            solution=(f'切向力与位置矢量垂直，τ=rF={r*f} N·m，逆时针为正。' if n%2==0 else f'力臂是轴到力作用线的垂直距离d，τ=dF={r*f} N·m，逆时针为正。'),
            hints=['力矩取决于力与力臂。','切向力的力臂等于到转轴的距离。' if n%2==0 else '力臂是轴到力作用线的垂直距离，不是任意位置矢量的长度。','力矩等于力乘以力臂，并按约定确定正负号。'],conditions=['固定转轴','切向力' if n%2==0 else '给定垂直力臂','逆时针为正'],unit='N·m')
    if model == 'angular_acceleration':
        inertia,tau=2+n%17,4+n%23
        return dict(subject='mechanics',parameters={'inertia':inertia,'torque':tau},answer=str(Fraction(tau,inertia)),
            stem=(f'刚体绕固定主轴转动，转动惯量恒为 {inertia} kg·m²，沿该轴合力矩为 {tau} N·m。求角加速度（rad/s²）。' if n%2==0 else f'飞轮绕固定主轴转动，转动惯量恒为 {inertia} kg·m²，恒定合力矩 {tau} N·m 作用 1 s，求角速度增加量（rad/s）。'),
            solution=(f'固定主轴转动方程 τ=Iα，α=τ/I={Fraction(tau,inertia)} rad/s²。' if n%2==0 else f'τ=Iα，Δω=αΔt=(τ/I)×1 s={Fraction(tau,inertia)} rad/s。'),
            hints=['转动中什么量对应平动的质量？','固定轴转动满足合力矩 τ=Iα。','求出角加速度；若求角速度增量，再乘作用时间。'],conditions=['固定主轴','转动惯量恒定'],unit='rad/s²' if n%2==0 else 'rad/s')
    if model == 'normalization':
        length=1+n%97
        return dict(subject='quantum',parameters={'length':length},answer=f'1/sqrt({length})',
            stem=f'一维波函数在 $0<x<{length}\\,\\mathrm{{m}}$ 内为常数 $A$，区间外为零。选取 $A$ 为正实数，求归一化常数 $A$（$\\mathrm{{m}}^{{-1/2}}$）。',
            solution=f'归一化条件 ∫|ψ|²dx=1 给出 A²×{length}=1，因此 A=1/sqrt({length}) m^(-1/2)。',
            hints=['总概率必须为 1。','对全空间积分 |ψ|²。','常数波函数给出 A²L=1，并取正实根。'],conditions=['正实数振幅','有限区间','区间外为零'],unit='m^(-1/2)')
    if model == 'rope_no_slip':
        radius,alpha=1+n%3,1+n%11
        a=Fraction(radius*alpha,10)
        return dict(subject='mechanics',parameters={'radius_dm':radius,'alpha':alpha},answer=str(a),
            stem=f'轻绳与定轴圆轮的轮缘不滑动，轮心固定，半径为 {radius}/10 m，当前角加速度大小为 {alpha} rad/s²。求绳沿自身方向的切向加速度大小（m/s²）。',
            solution=f'绳速等于轮缘切向速度v=ωR，R恒定，求导得绳的切向加速度a=αR={a} m/s²。',
            hints=['区分绳的运动与固定轮心。','不滑动使绳速等于轮缘切向速度v=ωR。','R恒定，对时间求导；所求不是轮心加速度。'],
            conditions=['定轴且轮心固定','半径恒定','绳与轮缘不滑动','所求为绳的切向加速度'],unit='m/s²')
    if model == 'pulley':
        m,j,r=1+n%7,2+n%11,1+n%3
        a=Fraction(10*m*r*r,m*r*r+j)
        return dict(subject='mechanics',parameters={'mass':m,'inertia_scaled':j,'radius_dm':r,'gravity':10},answer=str(a),
            stem=f'定轴滑轮的转动惯量为 {j}/100 kg·m²，半径为 {r}/10 m。轻绳一端固定并缠绕轮缘，另一端悬挂 {m} kg 重物。绳绷紧且与轮缘不滑动，忽略空气阻力和轴承摩擦，半径恒定，由静止释放；取g=10 m/s²。求重物下降加速度大小（m/s²）。',
            solution=f'以重物向下为正：mg−T=ma；滑轮转动方程TR=Iα；绳不滑动给出a=αR。消去T、α，a=mg/(m+I/R²)={a} m/s²。',
            hints=['同时考虑重物平动、滑轮转动和绳不滑动三个关系。','分别列mg−T=ma和TR=Iα；T是绳张力。','用a=αR把α换成a/R，再消去T；先保留符号再代数求解。'],
            conditions=['固定转轴','轻且不可伸长的绳','绳绷紧且无滑动','半径与转动惯量恒定','忽略空气阻力与轴承摩擦','由静止释放'],unit='m/s²')
    raise ValueError('unsupported canonical model')


def generate(model, topic_id, variant=0):
    data=canonical(model,variant)
    # Keep v1 keys for the original two families to preserve existing stable IDs.
    version=1 if model in ('newton','born') else 2
    key=hashlib.sha256(f'{model}:{topic_id}:{variant}:v{version}'.encode()).hexdigest()[:16]
    hints={str(i+1):value for i,value in enumerate(data['hints'])}
    record={'id':'GEN-'+key,'subject':data['subject'],'topic_ids':[topic_id],'difficulty':3 if model=='pulley' else 1,
        'question_type':'symbolic' if model=='normalization' else 'numeric','stem':data['stem'],
        'correct_answer':data['answer'],'solution':data['solution'],'source_type':'ai_generated',
        'verified':False,'human_verified':False,'machine_validated':False,'content_status':'solution_draft',
        'generation':{'model':model,'variant':variant,'version':version,'parameters':data['parameters'],'status':'generated','source':'local_canonical'},
        'hints':hints,'hint':hints['1'],'estimated_minutes':2,'time_source':'template_estimate',
        'difficulty_source':'template_design','physical_conditions':data['conditions'],'answer_unit':data['unit']}
    record['generation']['status']='validating'
    from .generated_validation import validate_generated
    record['validation']=validate_generated(record)
    record['generation']['status']=record['validation']['status']
    record['machine_validated']=record['validation']['passed']
    record['content_status']='practice_ready' if record['machine_validated'] else 'needs_review'
    return record
