from pathlib import Path
import json,csv,hashlib,re
from pypdf import PdfReader
R=Path(__file__).resolve().parent
metadata={}
for f in (R/'教程').glob('*记录.json'):
 for item in json.loads(f.read_text(encoding='utf-8')):
  if item.get('file'): metadata[Path(item['file']).name]=item
rows=[]
for p in sorted((R/'教程').rglob('*.pdf')):
 reader=PdfReader(p); raw=p.read_bytes(); m=metadata.get(p.name,{})
 rows.append(dict(file=str(p.relative_to(R)),pages=len(reader.pages),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),source=m.get('url',m.get('source','见下载记录')),role='补充资料，非大纲指定版本',status='可用PDF；已核验文件结构及页数'))
(R/'PDF资源清单.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
with (R/'PDF资源清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
md=['# 可用PDF资源清单',f'共 {len(rows)} 份补充PDF。指定六册教材尚未取得普通PDF。页数仅表示文件结构校验，不代表已逐页校对内容。','|文件|页数|来源|','|---|---:|---|']
for q in rows:
 md.append(f"|[{Path(q['file']).name}]({q['file'].replace(chr(92),'/').replace(' ','%20')})|{q['pages']}|{q['source']}|")
(R/'PDF资源清单.md').write_text('\n'.join(md),encoding='utf-8')
groups=[
('1,2,3,4,5','傅里叶归一化|有限支撑态概率与矩|动量表象的位置算符|高斯态动量矩|Buffon概率（拓展）'),
('1,2,3,4,5,6,7,8,9','定态正交性|叠加态位置随时间|内积守恒|能量实数性|虚势与衰减（拓展）|Ehrenfest定理|势阱热布居（拓展）|无限深势阱不确定性|期望值振荡'),
('1,2,3,4a,4b','半无限势阱束缚条件|环上粒子量子化|正弦立方初态演化|势阱中δ势|双势阱模型'),
('1,2,3,4,5,6,7,8','Hermite递推与位置矩阵|动量矩阵|谐振子不确定性|半谐振子|阶梯势反射透射|量子与经典比较|Griffiths 2.38（需外部题干）|Griffiths 2.39（需外部题干）'),
('1,2,3,4,5','自旋谱分解|Dirac内积与范数|对易矩阵|迹与厄密乘积|反厄密算符'),
('0,1,2,3,4,5,6','角动量对易|Sy本征态|自旋期望值|任意方向自旋测量|两能级对角化|Pauli矩阵指数|自旋旋转'),
('1,2,3,4','自旋时间演化|矩阵表象|两能级振荡|基底相位不变性'),
('1,2,3,4,5','谐振子动量表象|位置本征函数|动量厄密性|动量矩阵|定态平均动量'),
('1,2,3,4,5','横向角动量期望|角动量平方对易|角动量不确定性|球谐与Lx|正则对易运算'),
('1,2,3,4,5,6,7,8','Heisenberg自旋演化|恒定电场演化|磁场近似守恒|谐振子动能矩|含时相干态（拓展）|l=1矩阵|压缩态（拓展）|二次型谐振子（拓展）'),
('0,1,2,3,4,5,6','矢量对易|径向动量|Hellmann-Feynman关系|对数势位力定理|氢原子不确定性|球势阱压力|量子亏损（拓展）'),
('1,2,3','两能级微扰与精确解|势阱δ微扰|转子弱磁场'),
('1,2,3,4,5,6,7','三阶矩阵微扰|二维势阱简并|环势简并微扰|角动量耦合系数|耦合态测量|耦合态Sz|相对论能量修正'),
('1,2,3','强场Zeeman|弱场Zeeman|n=3 Stark效应'),
('1,2,3,4,5,6,7','单重态关联|两自旋交换演化|三自旋能级|两自旋1耦合|全同粒子谐振子（拓展）|Pauli乘积对易|占据数计数（拓展）'),
('1,2,4','两能级含时跃迁|谐振子偶极选择规则|氢原子脉冲跃迁')]
idx=[]
for n,(numbers,topics) in enumerate(groups,1):
 for num,t in zip(numbers.split(','),topics.split('|')):
  idx.append(dict(id=f'BNU-HW{n:02}-{num}',topic=t,source=f'../教程/北师大量子力学/hw{n}.pdf',page=1,original_number=num,answer_set=f'../教程/北师大量子力学/hw{n}_ans.pdf',status='需外部题干' if '外部题干' in t else '源PDF题目索引',answer_status='配套答案整套链接；逐题对应待核对'))
(R/'题库/课程习题索引.json').write_text(json.dumps(idx,ensure_ascii=False,indent=2),encoding='utf-8')
md=['# 北师大量子力学课程习题索引',f'{len(idx)} 条索引，其中2条需外部教材题干。题干保留在源PDF，不声称已逐题校对答案；第3套原卷题号重复，使用4a/4b区分。','|ID|主题|题目|配套答案|','|---|---|---|---|']
for q in idx:md.append(f"|{q['id']}|{q['topic']}|[PDF第1页]({q['source']})|[整套答案，待核对]({q['answer_set']})|")
(R/'题库/课程习题索引.md').write_text('\n'.join(md),encoding='utf-8')
readme=f'''# 考研专业课资料与题库

打开 [离线题库](题库/物理考研题库.html)。49道原创基础题含答案和易错点；63条真题索引来自本地3份原卷；另有{len(idx)}条[课程习题索引](题库/课程习题索引.md)，其中2条需外部题干。索引条目不等于已整理完整题干和解析的题目。

## PDF资料

已整理{len(rows)}份有效PDF，见[资源清单](PDF资源清单.md)。包含Tong量子力学、统计物理、电磁学，北师大量子力学完整讲义、16套作业及16套配套答案，以及3份本地辅助资料。所有下载脚本使用无代理DIRECT连接；下载记录保留来源、页数及SHA256。部分课程习题超出大纲，已在主题中标注拓展；无标注也应结合大纲选用。

## 指定教材缺口

赵凯华《新概念物理教程》力学第二版2004、热学第二版2005、电磁学第二版2006、光学2004、量子物理第二版2008，以及曾谨言《量子力学教程》2003，均未取得符合要求的普通PDF。补充讲义不冒充这六册教材。

科学文库已登录并执行下载：曾谨言2003版下载文件只有DRM阅读器提示页，需要专用科学文库阅读器，因此排除有效PDF成果。在线阅读全文和PDG也不计入。清华光学讲义及Tong动力学下载失败，记录保留，未计入有效清单。光学、原子与核物理教材仍是主要资料缺口。

## 工作方式

借鉴[whzy3185/kaoyan八周计划](https://github.com/whzy3185/kaoyan/blob/main/408_8_WEEK_PLAN.md)的闭卷回忆、重建知识、最小验证、错因复盘、延迟复测流程，迁移到本地651普通物理与803量子力学大纲。见[八周安排](八周复习安排.md)和[大纲主题对应表](大纲教材对应表.md)。35个大主题有基础题入口，不表示全部细分考点已覆盖。

## 使用

1. 每次闭卷做题，再展开答案；记录启动困难、条件、公式、符号、单位或计算错因。
2. 题库按3天和14天安排复测；连续两次延迟独立正确作为阶段稳定标志。浏览器本地保存进度，定期点击导出记录备份；清理浏览器数据会丢失记录。
3. 本地仅有23普物、24普物、24量子三卷，默认冻结为模拟卷。真题页面需主动解锁；查看一页会同时暴露邻题。原卷无官方答案。
4. 课程作业先打开题目PDF，再看答案整套。发现HW1部分题号与答案不严格对应，故全部答案链接保留待核对状态。

生成脚本可复现；不要重新运行制作题库.py覆盖手动页面修改。此目录保留中间搜索记录，最终有效文件以PDF资源清单为准。
'''
(R/'README.md').write_text(readme,encoding='utf-8')
(R/'八周复习安排.md').write_text('''# 八周复习安排

每次学习：闭卷回忆 → 查讲义补缺 → 1～3题最小验证 → 错因记录 → 3天及14天复测。时间依个人安排，不假定每日学习小时数。

|周|普通物理|量子力学|验收|
|---|---|---|---|
|1|力学、刚体、振动波|概率解释、归一化|独立列式；完成基础诊断|
|2|气体动理论、热力学|一维势阱、谐振子|边界、能级、单位无误；复测第1周|
|3|静电场、电势、电容|算符、表象、不确定性|掌握对易与守恒；复测第2周|
|4|磁场、感应、回路、Maxwell|自旋、角动量、Landau能级|条件与符号检查；复测第3周|
|5|干涉、衍射、偏振|中心势、氢原子|完成主线覆盖；光学资料待补|
|6|相对论、原子、核与量子基础|微扰、变分、含时跃迁|补细分大纲缺口；原子核资料待补|
|7|23普物限时模拟与复盘|课程题组合诊断|普物180分钟；按错因回到资料|
|8|24普物限时模拟|24量子限时模拟|各180分钟；保留错因及得分证据|

三份真题在对应模拟周之前冻结。基础入口不等于完成全部大纲；每周用大纲原文核对遗漏，答案不确定的课程题不标记为已掌握。
''',encoding='utf-8')
print(f'有效PDF {len(rows)}；课程索引 {len(idx)}；整理完成')
p=R/'题库/物理考研题库.html'
s=p.read_text(encoding='utf-8')
if '91条课程习题索引' not in s:
 s=s.replace('<a href="基础题库与解析.md">完整解析</a>','<a href="基础题库与解析.md">完整解析</a> · <a href="课程习题索引.md">91条课程习题索引</a>')
p.write_text(s,encoding='utf-8')
