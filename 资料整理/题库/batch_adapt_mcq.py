#!/usr/bin/env python3
"""用 DeepSeek 将教材题批量改编为单项选择题草稿。
密钥只从 DEEPSEEK_API_KEY/GENAI_API_KEY 读取；输出默认不进入推荐器。
"""
import argparse, json, os, time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[2]
BANK=ROOT/'资料整理'/'题库'/'教材习题.json'
OUT=ROOT/'资料整理'/'题库'/'deepseek选择题改编.json'

def call(base,key,model,prompt):
    url=base.rstrip('/')+'/chat/completions'
    body=json.dumps({'model':model,'messages':[{'role':'system','content':'你是考研物理命题教师。只输出合法 JSON，不输出 Markdown。不得改变原题考查的物理结论，不得补造原题没有给出的数值条件。'}, {'role':'user','content':prompt}], 'temperature':0.2,'max_tokens':2500}).encode()
    req=Request(url,data=body,headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
    with urlopen(req,timeout=120) as r: data=json.loads(r.read())
    text=data['choices'][0]['message']['content'].strip()
    if text.startswith('```'): text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
    return json.loads(text)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int,default=20);ap.add_argument('--start',type=int,default=0);ap.add_argument('--resume',action='store_true');ap.add_argument('--output',default=str(OUT));args=ap.parse_args()
    key=os.getenv('DEEPSEEK_API_KEY') or os.getenv('GENAI_API_KEY');base=os.getenv('DEEPSEEK_BASE_URL') or os.getenv('GENAI_BASE_URL') or 'https://genaiapi.shanghaitech.edu.cn/api/v1/start';model=os.getenv('DEEPSEEK_MODEL') or os.getenv('GENAI_MODEL') or 'deepseek-pro'
    if not key or not base: raise SystemExit('缺少 DEEPSEEK_API_KEY/GENAI_API_KEY 或 DEEPSEEK_BASE_URL/GENAI_BASE_URL')
    bank=json.loads(BANK.read_text(encoding='utf-8')); questions=bank['questions'] if isinstance(bank,dict) else bank
    existing=[]
    if args.resume and Path(args.output).exists(): existing=json.loads(Path(args.output).read_text(encoding='utf-8')).get('questions',[])
    done={x['source_id'] for x in existing}; pool=[q for q in questions if q.get('question_ocr') and q.get('id') not in done][args.start:args.start+args.limit]
    for n,q in enumerate(pool,1):
        prompt=f'''把下面教材题改编成考研物理单项选择题。保留原知识点和难度层级，允许改变数字或情境但必须保证只有一个正确选项。输出对象字段：statement（题干，含必要条件）、options（恰好4个字符串，前缀A-D）、answer（A/B/C/D）、explanation（简明推导）、topic、adaptation_notes。题面可能有OCR错误；看不清的符号不要猜，返回 needs_review=true 并说明疑点。原题ID：{q['id']}\n原题：{q['question_ocr']}'''
        try:
            item=call(base,key,model,prompt); item.update({'id':'ADP-'+q['id'],'source_id':q['id'],'type':'选择题','status':'draft','recommendation_eligible':False,'generated_by':model,'needs_review':bool(item.get('needs_review',False))}); existing.append(item)
        except Exception as e:
            existing.append({'id':'ADP-'+q['id'],'source_id':q['id'],'type':'选择题','status':'error','error':str(e),'recommendation_eligible':False})
        Path(args.output).write_text(json.dumps({'version':'2026-10-10','policy':'DeepSeek改编草稿，人工核验前不推荐','questions':existing},ensure_ascii=False,indent=2),encoding='utf-8'); print(f'{n}/{len(pool)} {q["id"]}'); time.sleep(.2)
if __name__=='__main__': main()

