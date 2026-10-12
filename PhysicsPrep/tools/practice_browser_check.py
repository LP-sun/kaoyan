"""Real browser/process acceptance on an isolated DB; never clears user data.

--minutes 30 paces actual UI interactions for a 30-minute automated session.
The answers are test oracles, NOT evidence of human learning improvements.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

parser=argparse.ArgumentParser()
parser.add_argument('--questions',type=int,default=20)
parser.add_argument('--minutes',type=float,default=0)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
folder=Path(tempfile.mkdtemp(prefix='physicsprep-practice-check-'))
db=folder/'study.sqlite3'
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
base=f'http://127.0.0.1:{port}'
env=dict(os.environ,PHYSICSPREP_PORT=str(port),PHYSICSPREP_DB_PATH=str(db),
    PHYSICSPREP_OPEN_BROWSER='false',APP_MOCK_MODE='true',GRADIO_ANALYTICS_ENABLED='False')
process=None
log=(folder/'server.log').open('ab')

def start():
    global process
    process=subprocess.Popen([sys.executable,'app.py'],cwd=root,env=env,stdout=log,stderr=log,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(60):
        if process.poll() is not None: raise RuntimeError('isolated server exited')
        try:
            urllib.request.urlopen(base,timeout=1).close(); return
        except Exception: time.sleep(.5)
    raise RuntimeError('isolated server startup timed out')

def stop():
    if process and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=8)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)

def current():
    with sqlite3.connect(db) as conn:
        snapshot=conn.execute("SELECT current_snapshot FROM exam_sessions WHERE status='active' ORDER BY started_at DESC LIMIT 1").fetchone()
        return json.loads(snapshot[0])

def count():
    with sqlite3.connect(db) as conn:
        return conn.execute('SELECT count(*) FROM attempts').fetchone()[0]

def fill(page,q,wrong=False):
    expected=q['correct_answer']; kind=q['question_type']
    if kind=='single_choice':
        value='B' if wrong and expected=='A' else 'A' if wrong else expected
        page.locator('#practice-radio label').filter(has_text=re.compile(rf'\b{value}\.')).click()
    elif kind=='multiple_choice':
        values=[next(chr(65+i) for i in range(len(q['options'])) if chr(65+i) not in expected)] if wrong and len(expected)<len(q['options']) else expected[:1] if wrong else expected
        for v in values:
            page.locator('#practice-many label').filter(has_text=re.compile(rf'\b{v}\.')).click()
    else:
        page.locator('#practice-answer textarea').fill('0' if wrong else str(expected))

try:
    print(f'Artifacts: {folder}',flush=True)
    start()
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        page=browser.new_page(viewport={'width':1400,'height':950})
        page.goto(base)
        page.locator('#practice-start').click()
        expect(page.locator('#practice-submit')).to_be_enabled(timeout=30000)
        begun=time.monotonic(); seen=[]
        total=max(args.questions,40 if args.minutes else args.questions)
        for i in range(total):
            q=current(); seen.append(q['id'])
            assert q['id'] in page.locator('#practice-meta').inner_text()
            assert '标准答案' not in page.locator('#practice-card').inner_text()
            if i%7==3:
                page.locator('#practice-hint-button').click()
                expect(page.locator('#practice-hint')).not_to_be_empty(timeout=30000)
            if args.minutes:
                # Actual wall time, no injected timestamps or fake histories.
                due=begun+(i+1)*args.minutes*60/total
                while time.monotonic()<due: time.sleep(min(1,due-time.monotonic()))
            fill(page,q,wrong=i%9==4)
            page.locator('#practice-submit').click()
            expect(page.locator('#practice-next')).to_be_enabled(timeout=30000)
            assert q['id'] in page.locator('#practice-meta').inner_text()
            assert count()==i+1
            print(f'PASS browser submission {i+1}/{total}',flush=True)
            page.locator('#practice-next').click()
            expect(page.locator('#practice-submit')).to_be_enabled(timeout=30000)
            if i==19 or (total<20 and i==total//2):
                before=current()['id']; old_count=count()
                stop(); start(); page.goto(base)
                page.locator('#practice-continue').click()
                expect(page.locator('#practice-submit')).to_be_enabled(timeout=30000)
                assert current()['id']==before and count()==old_count
                print('PASS real process restart and UI resume',flush=True)
        page.screenshot(path=str(folder/'continuous-practice.png'),full_page=True)
        page.locator('#practice-end').click()
        expect(page.locator('#practice-submit')).to_be_disabled(timeout=30000)
        browser.close()
        print(json.dumps({'questions':count(),'elapsed_seconds':round(time.monotonic()-begun,1),
            'distinct_ids':len(set(seen)),'artifacts':str(folder),'test_oracle_answers':True},ensure_ascii=False),flush=True)
except Exception:
    if 'page' in globals():
        try:
            page.screenshot(path=str(folder/'failure.png'),full_page=True)
            (folder/'failure-dom.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
        except Exception: pass
    raise
finally:
    stop(); log.close()
