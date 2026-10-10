from .selector import select_question
from .mastery import update_mastery

ERROR_CATEGORIES=['概念理解错误','公式使用错误','物理模型建立错误','受力 / 几何分析错误','数学计算错误','单位和量纲错误','审题错误','知识缺失','尚无法确定']

def error_analysis(status, question_type):
    if status=='correct': return '无', '本题表现正确；仍需其他题与延迟复测确认。'
    if status=='uncertain': return '尚无法确定', '输入或推导无法确定性判分，请检查表达式或人工复核。'
    return '尚无法确定', '仅凭最终答案不能可靠识别错因；可能涉及概念、公式、模型或计算，应通过前置题追问。'
