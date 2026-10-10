from pathlib import Path
import json,csv,html,re
ROOT=Path(__file__).parent
topics={
'力学':'质点运动学|牛顿定律与功能|动量与碰撞|刚体转动|振动与波|狭义相对论',
'热学':'气体分子运动论|热力学与熵',
'电磁学':'静电场|稳恒磁场|电磁感应|交直流电路|麦克斯韦方程与电磁波|国际单位制',
'光学':'光波与偏振态|光的干涉|光的衍射与仪器|偏振与双折射',
'原子物理':'原子量子态与精细结构|多电子原子|磁场中的原子|X射线|分子光谱|原子核|量子物理基础',
'量子力学':'早期量子现象|波粒二象性|一维势场|算符与表象|力学量与不确定性|电子自旋|角动量与Landau能级|中心势与氢原子|定态微扰与变分|含时微扰'}
data='''力学|质点运动学|计算|质点 r(t)=(2t²,3t) m，求 t=1 s 的速度、加速度及曲率半径。|v=(4,3) m/s，a=(4,0) m/s²。速率5，ρ=|v|³/|v×a|=125/12 m。|曲率使用法向加速度，不能直接用总加速度。
力学|牛顿定律与功能|计算|质量2 kg的物体在光滑水平面由静止出发，沿x方向受力F=3x N；运动到x=2 m时速度多大？|功∫₀²3x dx=6 J，mv²/2=6，v=√6 m/s。|变力功须积分。
力学|动量与碰撞|计算|质量m的小球以v撞上静止的质量2m小球，完全非弹性碰撞，无外冲量。求共同速度及损失动能。|共同速度v/3；初动能mv²/2，末动能mv²/6，损失mv²/3。|动量守恒不等于动能守恒。
力学|刚体转动|计算|均匀实心球从高度h沿斜面无滑动滚下，I=2mR²/5，求质心速率。|mgh=mv²/2+I(v/R)²/2=7mv²/10，v=√(10gh/7)。|无滑动约束v=ωR。
力学|振动与波|计算|两列波y₁=Acos(kx−ωt)、y₂=Acos(kx+ωt)叠加，写合成波及波节位置。|y=2Acos(kx)cos(ωt)；波节kx=(n+1/2)π；相邻波节间距λ/2。|驻波振幅随位置变。
力学|狭义相对论|计算|两飞船在地面系分别以+0.8c、−0.8c运动，一船测另一船速率多少？|速度变换u′=(u−v)/(1−uv/c²)，大小1.6c/1.64=40c/41。|不能直接相加得到1.6c。
热学|气体分子运动论|简答|理想气体分子的最概然、平均和方均根速率分别是什么？|v_mp=√(2kT/m)，平均速率√(8kT/(πm))，v_rms=√(3kT/m)；v_mp<平均速率<v_rms。|比较速率而非速度矢量平均值。
热学|热力学与熵|计算|1 mol单原子理想气体从T₀可逆等容升温到2T₀，求W、Q、ΔS。约定气体对外做功为正。|W=0，Q=ΔU=3RT₀/2；ΔS=∫C_V dT/T=3Rln2/2。|熵变须通过可逆路径计算。
热学|热力学与熵|计算|卡诺热机工作于600 K和300 K之间，每周期吸热200 J。求效率、功、排热。|η=1−300/600=1/2；W=100 J，Q_c=100 J。|温度必须使用K。
电磁学|静电场|计算|真空同心球电容器内外半径a、b，b>a。推导电容。|E=Q/(4πε₀r²)，V=Q(1/a−1/b)/(4πε₀)，C=4πε₀ab/(b−a)。|积分方向与电势差保持一致。
电磁学|稳恒磁场|计算|无限长直导线电流I，求距导线r处磁场及方向。|安培环路B·2πr=μ₀I，B=μ₀I/(2πr)；方向按右手定则。|应用环路定理须有对称性。
电磁学|电磁感应|计算|N匝面积S线圈在匀强磁场B中转动，法线与B夹角ωt，求感应电动势。|Φ=NBS cos(ωt)，按所选正向ε=−dΦ/dt=NBSωsin(ωt)。|先约定面积正向再判断符号。
电磁学|交直流电路|计算|电源ε经R给初始无电荷的C充电，求q(t)及电流。|R dq/dt+q/C=ε；q=Cε(1−e^(−t/RC))；i=εe^(−t/RC)/R。|充电初期电流最大。
电磁学|麦克斯韦方程与电磁波|简答|圆形平行板电容器半径R，充电电流I，忽略边缘效应，求板间距轴r<R处的B。|位移电流穿过半径r圆面为I r²/R²；B·2πr=μ₀I r²/R²；B=μ₀Ir/(2πR²)，方向沿环向。|位移电流随所选面积变化。
电磁学|国际单位制|填空|写出电容、电感、磁通量、磁感应强度的SI单位，并给出关系。|F，H，Wb，T；1 Wb=1 V·s，1 T=1 Wb/m²，1 H=1 Wb/A，1 F=1 C/V。|磁通量与磁感应强度单位不同。
光学|光波与偏振态|简答|E_x=E₀cos(kz−ωt)，E_y=E₀cos(kz−ωt+π/2)，判断偏振态。|相互垂直的等幅分量相差π/2，合成圆偏振光；旋向需说明观察方向和相位约定。|旋向不能脱离观察方向判断。
光学|光的干涉|计算|杨氏双缝间距0.50 mm，屏距2.0 m，波长500 nm，求条纹间距。|Δx=λD/d=2.0 mm，采用远场小角近似。|单位须转换成米。
光学|光的干涉|计算|迈克尔孙干涉仪中反射镜移动0.15 mm，数到500条条纹，求波长。|2Δd=Nλ，λ=600 nm。|光程差变化是镜移的2倍。
光学|光的衍射与仪器|计算|单缝宽0.20 mm，波长500 nm，焦距0.40 m。求焦平面中央主极大宽度。|第一暗纹a sinθ=λ；小角下中央宽度2fλ/a=2.0 mm。|中央宽度是从两侧第一暗纹之间算。
光学|光的衍射与仪器|计算|光栅有5000条被照亮刻线，二级光谱中λ=600 nm，最小可分辨波长差？|分辨本领R=mN=10000；Δλ=λ/R=0.060 nm。|N是照亮刻线总数。
光学|偏振与双折射|计算|非偏振光强I₀依次通过三个理想偏振片，透振方向0°、45°、90°，求出射光强。|I₁=I₀/2，I₂=I₀/4，I₃=I₀/8。|非偏振光通过第一片先减半。
光学|偏振与双折射|简答|等幅正交分量组成线偏振光，沿四分之一波片两主轴入射时如何得到圆偏振？|入射线偏振与主轴成45°，产生等幅分量；波片引入π/2相位差，输出圆偏振。|其他夹角通常输出椭圆偏振。
原子物理|原子量子态与精细结构|计算|类氢离子核电荷Z=2，电子n=3跃迁到n=2，忽略精细结构和约化质量修正，求光子能量。|E_n=−13.6Z²/n² eV；ΔE=54.4(1/4−1/9)=7.56 eV。|能级为负，光子能量为正差值。
原子物理|原子量子态与精细结构|简答|单电子电偶极跃迁中轨道角动量和磁量子数的选择规则是什么？|Δl=±1，Δm=0,±1，宇称改变；含自旋耦合时还需检查Δj=0,±1且j=0到0禁戒。|不能只检查能量下降。
原子物理|多电子原子|简答|两个非同科p电子在LS耦合下可有哪些L和S？同科时能直接使用所有组合吗？|l₁=l₂=1给L=0,1,2；s₁=s₂=1/2给S=0,1。非同科可组合这些值；同科受泡利反对称性限制，须筛选。|同科电子不能当可区分粒子。
原子物理|磁场中的原子|计算|LS耦合态l=1、s=1/2、j=3/2的Landé因子是多少？弱场能移如何写？|g_J=1+[j(j+1)+s(s+1)−l(l+1)]/[2j(j+1)]=4/3；ΔE=g_Jμ_B m_J B。|公式适用于弱场LS耦合。
原子物理|X射线|计算|康普顿散射角90°时波长增加多少？|Δλ=h(1−cosθ)/(m_ec)=h/(m_ec)≈2.426 pm，适用于初始近似静止自由电子。|波长差与入射波长无关。
原子物理|分子光谱|简答|刚性双原子转子的转动能级与电偶极转动跃迁规则是什么？|E_J=ℏ²J(J+1)/(2I)，J=0,1,…；有永久电偶极矩的分子满足ΔJ=±1。|同核双原子分子没有此类纯转动电偶极谱。
原子物理|原子核|计算|核反应质量亏损0.010 u对应多少释放能量？|Q=Δmc²≈0.010×931.5 MeV=9.315 MeV；前后质量必须使用一致的原子或核质量口径。|不能混用电子计数不一致的质量。
原子物理|量子物理基础|计算|非相对论电子经100 V加速，求德布罗意波长。|p=√(2m_e eV)，λ=h/p≈0.123 nm。|先验证eV远小于m_ec²。
量子力学|早期量子现象|计算|金属逸出功2.0 eV，入射光子能量3.5 eV，求遏止电压。|K_max=hν−W=1.5 eV，U_s=K_max/e=1.5 V。|光强不决定最大动能。
量子力学|波粒二象性|计算|一维波函数ψ=A exp(−α|x|)，α>0，求归一化常数与⟨x⟩。|1=2|A|²∫₀∞e^(−2αx)dx=|A|²/α，可取A=√α；概率密度为偶函数，⟨x⟩=0。|归一化用模方。
量子力学|一维势场|计算|质量m粒子处于0<x<L的无限深势阱，求E_n、ψ_n及基态位于左半区的概率。|E_n=n²π²ℏ²/(2mL²)，ψ_n=√(2/L)sin(nπx/L)，n≥1；基态左半概率1/2。|边界是ψ(0)=ψ(L)=0。
量子力学|一维势场|计算|V(x)=−gδ(x)，g>0，求束缚态能量及导数跃变条件。|ψ′(0⁺)−ψ′(0⁻)=−2mgψ(0)/ℏ²；ψ=√κ e^(−κ|x|)，κ=mg/ℏ²；E=−mg²/(2ℏ²)。|ψ连续，但导数不连续。
量子力学|一维势场|计算|谐振子处于第n个能量本征态，求ΔxΔp。|⟨x⟩=⟨p⟩=0；⟨x²⟩=ℏ(n+1/2)/(mω)，⟨p²⟩=mℏω(n+1/2)；ΔxΔp=ℏ(n+1/2)。|只有基态达到ℏ/2。
量子力学|算符与表象|计算|A矩阵为[[1,i],[-i,2]]，判断厄密性，求本征值。|A†=A，为厄密矩阵；det(A−λI)=λ²−3λ+1=0；λ=(3±√5)/2。|共轭和转置都要做。
量子力学|算符与表象|简答|定义幺正表象变换U，态和算符怎么变，哪些量不变？|约定新态|ψ′⟩=U|ψ⟩，则A′=UAU†；U†U=1；标量积、归一化、期望值和本征值不变。|另一种约定也可，但态和算符须一致。
量子力学|力学量与不确定性|简答|由[x,p]=iℏ写出不确定关系。若算符A无显含时间，什么条件保证对任意态⟨A⟩守恒？|ΔxΔp≥ℏ/2；d⟨A⟩/dt=(i/ℏ)⟨[H,A]⟩，若[H,A]=0则守恒。|某一特殊态期望不变不能证明算符守恒。
量子力学|电子自旋|计算|自旋态|+x⟩在Sz表象如何表示？测Sz的概率及平均值？|列向量(1,1)/√2；测±ℏ/2各概率1/2；⟨Sz⟩=0。|平均值零不表示测量可得零。
量子力学|电子自旋|简答|写两个自旋1/2的单重态及三个三重态。|单重态(|↑↓⟩−|↓↑⟩)/√2；三重态|↑↑⟩、(|↑↓⟩+|↓↑⟩)/√2、|↓↓⟩。|检查交换对称性。
量子力学|角动量与Landau能级|简答|写J²、Jz本征值以及J₊对|jm⟩的作用。|J²=ℏ²j(j+1)，Jz=ℏm；J₊|jm⟩=ℏ√[j(j+1)−m(m+1)]|j,m+1⟩，m=−j,…,j。|j为整数或半整数，轨道l只为非负整数。
量子力学|角动量与Landau能级|计算|忽略自旋，质量m电荷q粒子在匀强磁场B中二维运动，写Landau能级。|E_n=ℏω_c(n+1/2)，ω_c=|q|B/m；三维需另加p_z²/(2m)。|二维与三维能谱不同。
量子力学|中心势与氢原子|计算|类氢离子基态径向概率密度最概然半径是多少？核电荷为Z，忽略约化质量修正。|R₁₀∝e^(−Zr/a₀)；径向概率∝r²e^(−2Zr/a₀)，极大在r=a₀/Z。|三维概率密度最大位置与径向概率最大位置不同。
量子力学|中心势与氢原子|简答|无限深球势阱半径a的基态能量和归一化波函数是什么？|l=0，u(r)=√(2/a)sin(πr/a)，0<r<a；ψ=u(r)Y₀₀/r，Y₀₀=1/√(4π)；E=π²ℏ²/(2ma²)。|径向u的归一化是∫|u|²dr=1。
量子力学|定态微扰与变分|计算|一维谐振子加入微扰λx²，求第n态一级能移。|E_n^(1)=λ⟨n|x²|n⟩=λℏ(n+1/2)/(mω)。|先确认非简并与微扰足够小。
量子力学|定态微扰与变分|计算|H=[[0,ε],[ε,Δ]]，Δ>0，|ε|≪Δ，求低能态到二阶能量并用精确解核对。|精确低能量(Δ−√(Δ²+4ε²))/2；展开为−ε²/Δ+O(ε⁴/Δ³)，一级修正为0。|二阶分母是E₀−E₁=−Δ。
量子力学|定态微扰与变分|简答|变分法试探态能量为何给基态能量上界？简并微扰的第一步是什么？|展开于能量本征态，⟨H⟩=Σ|c_n|²E_n≥E₀；简并微扰先在简并子空间对角化微扰矩阵。|上界要求试探态属于H定义域且归一化。
量子力学|含时微扰|简答|V(t)从t=0作用于初态|i⟩，写到|f⟩的一级跃迁振幅与最低阶概率。|c_f^(1)(t)=−(i/ℏ)∫₀ᵗ V_fi(t′)e^(iω_fi t′)dt′，ω_fi=(E_f−E_i)/ℏ；f≠i时P≈|c_f^(1)|²。|一级振幅对应二阶概率。
量子力学|含时微扰|简答|写费米黄金规则并解释适用前提。|Γ=(2π/ℏ)|V_fi|²ρ(E_f)，ρ为单位能量末态密度，须满足能量共振条件；适用弱微扰、密集末态及足够长但耗尽可忽略的时间区间。|离散两能级长期演化不能直接用恒定速率。'''
bank=[]
for n,line in enumerate(data.splitlines(),1):
 s,topic,kind,q,a,trap=re.match(r'^(.*?)\|(.*?)\|(.*?)\|(.*?[。？])\|(.*)\|([^|]*)$',line).groups()
 bank.append(dict(id=f'PHY-B{n:03}',subject=s,topic=topic,type=kind,question=q,answer=a,pitfall=trap,source='按本地大纲原创基础练习；非真题、非教材原题',difficulty='基础至中等',reserved=False))
exams={
'23普物':[(1,'选择',1,'运动学'),(2,'选择',1,'角动量守恒'),(3,'选择',1,'行波与驻波'),(4,'选择',1,'绝热过程'),(5,'选择',2,'球电容器'),(6,'选择',2,'转动线圈感应'),(7,'选择',2,'单缝衍射'),(8,'选择',2,'光子动量'),(1,'填空',2,'功与动能'),(2,'填空',2,'波函数参数'),(3,'填空',3,'气体自由度'),(4,'填空',3,'电偶极远场'),(5,'填空',3,'自感磁能'),(6,'填空',3,'麦克斯韦方程积分式'),(7,'填空',3,'瑞利判据'),(8,'填空',3,'相对论德布罗意波长'),(3,'计算',3,'球体滚动与小振动'),(4,'计算',3,'连续粒子弹性碰撞'),(5,'计算',4,'卡诺热机与熵'),(6,'计算',4,'氢原子电荷分布电场电势'),(7,'计算',4,'RC充电'),(8,'计算',4,'双路径干涉'),(9,'计算',4,'波函数归一化与概率')],
'24普物':[(1,'选择',1,'运动学与曲率'),(2,'选择',1,'基本相互作用'),(3,'选择',1,'简谐振动判别'),(4,'选择',1,'麦克斯韦速率分布'),(5,'选择',1,'电感并联'),(6,'选择',1,'电磁波波速'),(7,'选择',1,'单缝衍射'),(8,'选择',2,'谐振子能级'),(1,'填空',2,'多普勒效应'),(2,'填空',2,'相对论速度合成'),(3,'填空',2,'卡诺效率'),(4,'填空',2,'电容器能量'),(5,'填空',2,'非均匀磁场电磁感应'),(6,'填空',2,'电磁波传播方向'),(7,'填空',2,'马吕斯定律'),(8,'填空',2,'离子电子组态'),(3,'计算',3,'小球与杆弹性碰撞'),(4,'计算',3,'驻波与行波分解'),(5,'计算',3,'热力学过程图'),(6,'计算',3,'带电载流导线与洛伦兹力'),(7,'计算',3,'位移电流与坡印亭矢量'),(8,'计算',4,'旋转偏振片'),(9,'计算',4,'定态能量归一化与概率')],
'24量子':[(1,'选择',1,'厄密算符定义'),(2,'选择',1,'类氢径向概率'),(3,'选择',1,'无限深势阱能级'),(4,'选择',1,'电偶极选择规则'),(5,'选择',1,'厄密矩阵'),(6,'选择',1,'Pauli矩阵，选项跨页'),(1,'简答',2,'波函数统计解释'),(2,'简答',2,'中心力场定态角动量'),(3,'简答',2,'δ势匹配'),(4,'简答',2,'期望值演化'),(5,'简答',2,'中心力场守恒量'),(6,'简答',2,'电磁场中薛定谔方程'),(1,'计算',2,'共同本征矢'),(2,'计算',2,'无限深球势阱'),(3,'计算',2,'不确定性与谐振子，跨页'),(4,'计算',3,'旧量子条件与磁场轨道'),(5,'计算',3,'矩阵微扰与精确解')]
}
true=[]
for stem,rows in exams.items():
 for num,kind,page,topic in rows:
  p=ROOT/'真题页面'/f'{stem}-p{page}-0.png'
  true.append(dict(id=f'{stem}-{kind}{num:02}',subject='量子力学' if '量子' in stem else '普通物理',year=2000+int(stem[:2]),section=kind,original_number=num,page=page,topic=topic,source_pdf=f'../../{stem}.pdf',image=f'../真题页面/{p.name}',question='以原卷图像为准；此条为大题索引，不是完整文字转录',answer=None,status='已逐页核对题号和主题；未提供官方答案',reserved=True))
out=ROOT/'题库';out.mkdir(exist_ok=True)
(out/'基础题库.json').write_text(json.dumps(bank,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'真题索引.json').write_text(json.dumps(true,ensure_ascii=False,indent=2),encoding='utf-8')
for name,records in [('基础题库.csv',bank),('真题索引.csv',true)]:
 with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
md=['# 大纲原创基础题库',f'共{len(bank)}题；用于首轮诊断，不代表已穷尽大纲。答案为独立推导，非官方评分答案。','先闭卷作答，再核对答案；2～3天及1～2周复测。']
for q in bank:md += [f"\n## {q['id']} · {q['subject']} · {q['topic']}\n",q['question'],f"\n答案与步骤：{q['answer']}\n",f"易错点：{q['pitfall']}\n"]
(out/'基础题库与解析.md').write_text('\n'.join(md),encoding='utf-8')
coverage=['# 大纲—教材—题库对应表','章号未核实，使用大纲主题定位，不臆造页码。','|科目/册|大纲主题|基础题ID|状态|','|---|---|---|---|']
for s,ts in topics.items():
 for topic in ts.split('|'):
  ids=[q['id'] for q in bank if q['topic']==topic]
  coverage.append(f"|{s}|{topic}|{', '.join(ids)}|{'已有基础入口，仍需教材分节题补全' if ids else '缺口'}|")
(ROOT/'大纲教材对应表.md').write_text('\n'.join(coverage),encoding='utf-8')
payload=json.dumps(bank,ensure_ascii=False).replace('</','<\\/')
truepayload=json.dumps(true,ensure_ascii=False)
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>物理考研题库</title><style>body{font:17px/1.8 system-ui;margin:0;background:#f3f5f8;color:#172638}main{max-width:980px;margin:30px auto;padding:20px}h1{margin-bottom:0}button,select,input{font:inherit;margin:5px;padding:8px;border:1px solid #b9c4d0;border-radius:8px}article{background:white;padding:24px;margin:18px 0;border-radius:14px}small{color:#536477}summary{cursor:pointer;color:#1e5d97}img{max-width:100%}.bar{position:sticky;top:0;background:#f3f5f8;padding:8px}textarea{width:95%;height:80px;font:inherit}label{white-space:nowrap}</style><main><h1>普通物理 · 量子力学题库</h1><p>闭卷回忆 → 教材补课 → 最小验证 → 错因记录 → 延迟复测</p><p>基础题为原创入门练习；真题仅索引原卷，默认冻结。学习记录保存在当前浏览器，可导出备份。</p><div class="bar"><select id="subject"><option value="">全部科目</option></select><input id="search" placeholder="搜索知识点 / 题目"><select id="mode"><option value="all">全部基础题</option><option value="wrong">错题</option><option value="due">到期复测</option></select><button id="random">随机10题</button><button id="export">导出记录</button><button id="reset">显示全部</button></div><p id="stats"></p><section id="list"></section><details><summary>真题索引（默认保留卷）</summary><p>本地仅3份卷，暂全部保留。展开原卷会暴露真题；确认模拟卷安排后再练。</p><label><input type="checkbox" id="unlock">我现在要查看原卷索引</label><section id="true"></section></details><p><a href="../README.md">资料说明</a> · <a href="基础题库与解析.md">完整解析</a></p></main><script>const BANK=__BANK__,TRUE=__TRUE__;let records={};try{records=JSON.parse(localStorage.getItem('physics-records-v1')||'{}')}catch(e){}let randomIds=null;const $=id=>document.getElementById(id),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));for(const s of [...new Set(BANK.map(q=>q.subject))])$('subject').add(new Option(s,s));function save(){try{localStorage.setItem('physics-records-v1',JSON.stringify(records))}catch(e){alert('浏览器保存失败，请导出记录备份。')}}function render(){let qs=BANK.filter(q=>(!$('subject').value||q.subject===$('subject').value)&&(!$('search').value||JSON.stringify(q).includes($('search').value))&&(!randomIds||randomIds.includes(q.id)));if($('mode').value==='wrong')qs=qs.filter(q=>records[q.id]?.status==='wrong');if($('mode').value==='due')qs=qs.filter(q=>records[q.id]?.due&&records[q.id].due<=Date.now());$('stats').textContent=`共 ${BANK.length} 道基础题 / ${TRUE.length} 条真题索引；当前显示 ${qs.length} 道。`;$('list').innerHTML=qs.map(q=>{const r=records[q.id]||{};return `<article><small>${q.id} · ${q.subject} · ${q.topic} · ${q.type}</small><p>${esc(q.question)}</p><details><summary>查看答案与易错点</summary><p>${esc(q.answer)}</p><p>易错点：${esc(q.pitfall)}</p></details><p><button onclick="mark('${q.id}',false)">做错 / 不会</button><button onclick="mark('${q.id}',true)">独立正确</button><small>${r.status==='wrong'?'待补课':r.streak>=2?'已连续两次独立正确':r.status==='ok'?'等待延迟复测':'未练'} ${r.due?'· 下次 '+new Date(r.due).toLocaleDateString():''}</small></p><textarea placeholder="记录错因：启动 / 条件 / 公式 / 符号 / 单位 / 计算" onchange="note('${q.id}',this.value)">${esc(r.note||'')}</textarea></article>`}).join('')}function mark(id,ok){let r=records[id]||{},now=Date.now();if(ok&&r.status==='ok'&&r.due&&now<r.due){alert('尚未到延迟复测日期，本次不增加连续正确次数。');return}r.streak=ok?(r.streak||0)+1:0;r.status=ok?'ok':'wrong';r.last=now;r.due=now+(ok&&r.streak>=2?14:3)*86400000;records[id]=r;save();render()}function note(id,v){records[id]={...(records[id]||{}),note:v};save()}['subject','search','mode'].forEach(id=>$(id).oninput=()=>{randomIds=null;render()});$('random').onclick=()=>{let qs=BANK.filter(q=>!$('subject').value||q.subject===$('subject').value);for(let i=qs.length-1;i>0;i--){let j=Math.floor(Math.random()*(i+1));[qs[i],qs[j]]=[qs[j],qs[i]]}randomIds=qs.slice(0,10).map(q=>q.id);render()};$('reset').onclick=()=>{randomIds=null;$('subject').value='';$('search').value='';$('mode').value='all';render()};$('export').onclick=()=>{let url=URL.createObjectURL(new Blob([JSON.stringify(records,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='物理题库学习记录.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};$('unlock').onchange=()=>$('true').innerHTML=$('unlock').checked?TRUE.map(q=>`<article><small>${q.id} · 原卷第${q.page}页</small><p>${esc(q.topic)}</p><a href="${q.source_pdf}">打开完整原卷</a><details><summary>显示所在页（会同时暴露邻题）</summary><img loading="lazy" src="${q.image}"></details><p>${esc(q.status)}</p></article>`).join(''):'';render();</script></html>'''
(out/'物理考研题库.html').write_text(page.replace('__BANK__',payload).replace('__TRUE__',truepayload),encoding='utf-8')
assert len(true)==63 and len({q['id'] for q in true})==63
assert all((out/q['image']).exists() and (out/q['source_pdf']).exists() for q in true)
assert all(any(q['topic']==t for q in bank) for ts in topics.values() for t in ts.split('|'))
print(f'基础题 {len(bank)}；真题索引 {len(true)}；大纲主题 {sum(len(ts.split("|")) for ts in topics.values())}；唯一ID、文件路径及主题入口检查通过。')

