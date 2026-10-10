"""仅依据本地大纲与逐题 OCR 做可审计的初筛，不替代原页逐题复核。"""
import json, csv, re
from pathlib import Path
from collections import Counter
R = Path(__file__).resolve().parent
T = R / '题库'
# 科目、主题、要求、所在大纲PDF页、限定教材、题面检索词。
rules = []
def add(exam, topic, level, page, books, words):
    rules.append(dict(exam=exam, topic=topic, level=level, syllabus_page=page,
                      books=books.split(), keywords=words.split('|')))
add('651','质点运动学','熟练',1,'BK04','速度|加速度|运动方程|圆周运动|参考系|位移|矢径|切向|法向')
add('651','牛顿定律与功能','熟练',1,'BK04','牛顿|受力|摩擦|动能|势能|功率|机械能|保守力|斜面|弹簧')
add('651','动量与碰撞','熟练',1,'BK04','动量|冲量|碰撞|反冲')
add('651','刚体转动','熟练',1,'BK04','刚体|转动惯量|力矩|角动量|转动|滚动|圆柱|质心')
add('651','振动与波','熟练',1,'BK04','振动|振幅|相位|波动|驻波|多普勒|谐振|波长|波速')
add('651','狭义相对论','掌握',1,'BK04','相对论|洛伦兹|洛仑兹|伽利略|光速|同时性|质能')
add('651','气体分子运动论','掌握',2,'BK07','理想气体|压强|速率分布|麦克斯韦|玻耳兹曼|自由度|均分|输运|平均自由程|黏滞|粘滞|扩散')
add('651','热力学','掌握',2,'BK07','热力学|内能|卡诺|循环|熵|嫡|绝热|等温|热容|热机')
add('651','静电场','混合要求',2,'BK05','库仑|电场|电势|高斯|电容|电介质|静电|电荷|极化')
add('651','稳恒磁场','混合要求',2,'BK05','磁感应|毕奥|萨伐尔|安培|洛伦兹力|洛仑兹力|磁场|载流|磁矩')
add('651','磁介质','了解',2,'BK05','磁介质|磁化|磁导率|铁磁|顺磁|抗磁')
add('651','电磁感应','混合要求',2,'BK05','电磁感应|法拉第|楞次|电动势|自感|互感|磁通')
add('651','直流与交流电路','混合要求',2,'BK05','电路|电阻|电流|电源|交流|阻抗|基尔霍夫|谐振|电桥')
add('651','麦克斯韦方程与电磁波','混合要求',2,'BK05','位移电流|麦克斯韦|电磁波|坡印廷|能流')
add('651','电磁学国际单位制','熟练',2,'BK05','国际单位制|SI制|单位制')
add('651','光波与偏振态','熟练',2,'BK01','波函数|偏振态|圆偏振|椭圆偏振|光波')
add('651','光的干涉','混合要求',2,'BK01','干涉|相干|杨氏|薄膜|牛顿环|迈克尔孙|尖劈|法布里|珀罗')
add('651','光的衍射与分光性能','混合要求',2,'BK01','衍射|光栅|半波带|夫琅|菲涅|巴俾|分辨|色散|自由光谱')
add('651','成像仪器','了解',3,'BK01','放大镜|显微镜|望远镜|成像|透镜|焦距|像差')
add('651','偏振与双折射','混合要求',3,'BK01','偏振|马吕|波片|双折射|布儒斯特|布鲁斯特|各向异性')
add('651','原子量子态与精细结构','混合要求',3,'BK06 BK08','氢原子|玻尔|卢瑟福|赫兹|精细结构|自旋|轨道|选择定则|碱金属')
add('651','多电子原子','熟练',3,'BK06 BK08','多电子|氦|泡利|电子组态|电子壳层|同科|周期表|价电子')
add('651','磁场中的原子','熟练',3,'BK06 BK08','塞曼|原子的磁矩|盖拉赫')
add('651','X射线','了解',3,'BK06 BK08','X射线|X 射线|康普顿|Compton|晶体衍射')
add('651','分子光谱','了解',3,'BK06 BK08','分子光谱|双原子|分子能级|分子的')
add('651','原子核','了解',3,'BK06 BK08','原子核|衰变|核反应|核能|放射性|半衰期')
add('651','量子物理基础','混合要求',3,'BK06 BK08','波粒|波函数|德布罗意|不确定|对易|一维|薛定谔')
for topic, page, words in [
 ('早期量子现象',1,'光电效应|康普顿|Compton|氢原子光谱|黑体'),
 ('波粒二象性',1,'物质波|德布罗意|波粒|波函数|统计解释|薛定谔|叠加态|自由粒子'),
 ('一维势场',1,'势阱|势垒|隧穿|一维|谐振子|δ函数|delta'),
 ('算符与表象',1,'算符|表象|狄拉克|Dirac|幺正|么正|正交|归一|态空间|标量积|海森堡图'),
 ('力学量与不确定性',1,'厄密|对易|不确定|本征|哈密顿|守恒量|期望值|平均值'),
 ('电子自旋',1,'自旋|泡利矩阵|Pauli|单重态|三重态|对角化'),
 ('角动量与Landau能级',1,'角动量|朗道|Landau'),
 ('中心势与氢原子',2,'中心势|球谐|氢原子|类氢|径向'),
 ('定态微扰与变分',2,'微扰|简并|变分|能量修正|能级修正'),
 ('含时微扰',2,'含时微扰|跃迁几率|跃迁概率|黄金规则|费米黄金|周期性微扰|选择规则')]:
    add('803',topic,'大纲列明',page,'BK06 BK08',words)

questions = json.loads((T/'教材习题.json').read_text(encoding='utf-8'))
overrides_path = T/'相关性人工修订.json'
overrides = json.loads(overrides_path.read_text(encoding='utf-8')) if overrides_path.exists() else {}
unknown = set(overrides) - {q['id'] for q in questions}
if unknown: raise ValueError(f'人工修订包含未知 ID: {unknown}')
# 可选富集：模型相关性判断（构建题库与推荐.py --deepseek 产出）。只读合并，缺失则跳过。
# 这是模型判断，不等于人工核验，仅供推荐打分与筛选参考。
ds_path = T/'deepseek相关性分析.json'
model_relevance = {}
if ds_path.exists():
    for x in json.loads(ds_path.read_text(encoding='utf-8-sig')):
        if x.get('relevance'): model_relevance[x['id']] = x['relevance']
rows=[]
for q in questions:
    book=q['id'].split('-')[0]; text=re.sub(r'\s+', '', q['question_ocr'])
    per_exam={}
    for exam in ['651','803']:
        hits=[]
        for rule in rules:
            if rule['exam']!=exam or book not in rule['books']: continue
            terms=[w for w in rule['keywords'] if re.sub(r'\s+','',w).lower() in text.lower()]
            if terms: hits.append(dict(topic=rule['topic'], requirement=rule['level'],
                terms=terms, syllabus_pdf='普物大纲.pdf' if exam=='651' else '量子大纲.pdf',
                syllabus_page=rule['syllabus_page']))
        # 仅了解主题且无其他证据，降为概念优先；未命中绝不推断超纲。
        if not hits:
            tier='待核'; confidence='低'; reason='题面未找到明确主题证据；不等于超纲，暂不自动推荐'
        elif all(h['requirement']=='了解' for h in hits):
            tier='概念了解';confidence='初筛';reason='命中大纲了解主题，先做概念题；复杂推导待核'
        else:
            tier='大纲候选';confidence='初筛';reason='题面命中大纲主题；相关性及解题深度仍需原页确认'
        per_exam[exam]=dict(tier=tier,confidence=confidence,evidence=hits,reason=reason)
    row=dict(id=q['id'],book_id=book,chapter=q['chapter'],type=q['type'],
        source_pdf=q['source_pdf'],source_pages=[z['pdf_page'] for z in q['regions']],
        exams=per_exam,review_status='自动初筛，未逐题原页复核',
        dependency_warning=bool(re.search('上题|前题|接上|上例',text)),
        estimated_minutes=6 if q['type']=='思考题' else 15,
        difficulty='未评定',version_role='补充旧版' if book=='BK08' else '大纲指定版')
    if q['id'] in overrides:
        patch=overrides[q['id']]
        allowed={'exams','review_status','dependency_warning','estimated_minutes','difficulty'}
        if set(patch)-allowed: raise ValueError('不支持的修订字段: '+q['id'])
        row.update(patch)
    if q['id'] in model_relevance:
        row['relevance']=model_relevance[q['id']]
    rows.append(row)
data=dict(method='local-syllabus-keyword-screen-v1+model-relevance',rules=rules,questions=rows)
(T/'考研相关性.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(T/'推荐数据.js').write_text('const RELEVANCE_DATA='+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+';',encoding='utf-8')
with (T/'考研相关性.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['题目ID','科目','初筛分层','主题','命中词','原页待核','依赖前题'])
    for row in rows:
        for exam,a in row['exams'].items():w.writerow([row['id'],exam,a['tier'],';'.join(h['topic'] for h in a['evidence']),';'.join(','.join(h['terms']) for h in a['evidence']),row['review_status'],row['dependency_warning']])
report=['# 逐题相关性初筛报告','依据本地两份大纲逐条处理题库 OCR。关键词匹配不是逐题语义审阅，也不是预测命题频率。','']
for exam in ['651','803']:
    counts=Counter(r['exams'][exam]['tier'] for r in rows)
    report.append(f'- {exam}：'+ '；'.join(f'{k} {v}题' for k,v in counts.items()))
report+=['','全体记录均保留 ID、来源页、命中主题及词语；未命中归待核，不直接标超纲。涉及“上题”等依赖的题不独立自动推荐。BK08旧版默认不推荐，避免跨版重复。','估时仅按题型初始化，难度尚未评定；复杂度不能仅从题干长短推定。','人工修订保存到题库/相关性人工修订.json（ID为键，允许字段见脚本），重跑初筛会保留修订。按题面原页核验后才能改为已核验。']
(T/'相关性初筛报告.md').write_text('\n'.join(report),encoding='utf-8')
print('\n'.join(report))
