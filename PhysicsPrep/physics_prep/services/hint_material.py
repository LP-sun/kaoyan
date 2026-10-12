"""Short local law reminders, usable even without a model connection."""
LAWS = {
 'PHY-MECH-KIN-001':('匀加速运动','加速度恒定时，v=v₀+at，或v²−v₀²=2aΔx。'),
 'PHY-MECH-DYN-001':('研究对象与合力','惯性系中，质量恒定时，合力F=ma。先选方向再列分量。'),
 'PHY-MECH-ENE-001':('功与机械能','只有保守力做功时K+U守恒；否则需要加入非保守力做功。'),
 'PHY-MECH-MOM-001':('动量与外力','系统总动量改变等于外力冲量；外力冲量可忽略时总动量守恒。'),
 'PHY-MECH-ROT-001':('转轴与质量分布','转动惯量I=∫r²dm；r是到指定转轴的垂直距离。'),
 'PHY-MECH-ROT-002':('合力矩与转动惯量','固定主轴且I恒定时，沿轴合力矩τ=Iα。'),
 'PHY-MECH-ROT-003':('无滑动约束','纯滚动满足v=ωR、a=αR；同时考虑平动和转动，检查摩擦条件。'),
 'PHY-MECH-ROT-TORQUE':('力臂与方向','τ=r×F；力矩大小等于力乘以力臂，力臂为轴到作用线的垂直距离。'),
 'PHY-MECH-OSC-001':('回复力','线性弹簧的力F=−kx，联立牛顿定律得到简谐运动方程。'),
 'PHY-QM-WF-001':('概率与归一化','归一化要求∫|ψ|²dx=1。积分覆盖整个空间，注意给定的相位约定。'),
 'PHY-QM-WF-002':('概率密度','区域概率为该区域内|ψ|²的积分；ψ本身不是概率。'),
 'PHY-QM-OP-001':('算符作用顺序','对易子[A,B]=AB−BA。把它作用到任意可微测试函数f，再使用乘积求导。'),
 'PHY-QM-STAT-001':('边界条件','无限深势阱边界波函数为零；允许波数由边界条件决定，再用E=ℏ²k²/(2m)。'),
 'PHY-QM-STAT-002':('谐振子能级','一维量子谐振子Eₙ=(n+1/2)ℏω，n为非负整数。'),
 'PHY-QM-SPIN-001':('Born规则','在正交归一基中，结果概率是对应振幅的模平方，并检查概率总和。'),
}


def local_hint(question, level):
    explicit=(question.get('hints') or {}).get(str(level))
    if explicit:
        return explicit
    topic=(question.get('topic_ids') or [''])[0]
    if topic not in LAWS:
        return question.get('hint') or '先列研究对象、已知量、未知量和适用条件，再给出你准备使用的物理定律。'
    concept,law=LAWS[topic]
    if level==1:
        return f'先考虑{concept}。这道题给了哪些相关条件？'
    if level==2:
        return law+' 请先列出关键方程，不急于计算。'
    return law+'\n下一步：把已知量与未知量分别对应到方程，先解符号关系，再检查单位或边界条件。你能写出这一步吗？'
