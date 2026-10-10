import httpx
import pytest
from physics_prep.diagnosis.math_grader import grade,controlled_parse,InputError
from physics_prep.config import Settings
from physics_prep.llm.client import OfficialGenAIClient,MockLLMClient,create_client

def test_choices():
    assert grade('A','A','single_choice')['status']=='correct'
    assert grade('B','A','single_choice')['status']=='incorrect'
    assert grade(['A','C'],['C','A'],'multiple_choice')['status']=='correct'
    assert grade(['A'],['C','A'],'multiple_choice')['status']=='incorrect'

def test_symbolic():
    assert grade('M*g*sin(theta)/(M+M/2)','2*g*sin(theta)/3','symbolic',allowed_symbols=['M','g','theta'])['status']=='correct'
    assert grade('sqrt(2*g*h)','sqrt(2*g*h)','symbolic')['status']=='correct'
    assert grade('g','2*g','symbolic')['status']=='incorrect'

@pytest.mark.parametrize('s',["__import__('os').system('whoami')",'g.__class__','[1,2]','(lambda:1)()','2**100000','x'*301,'1/0'])
def test_unsafe(s):
    assert grade(s,'1','symbolic')['status']=='uncertain'

def test_numeric_and_uncertain():
    assert grade('1.00000001','1','numeric')['status']=='correct'
    assert grade('2','1','numeric')['status']=='incorrect'
    assert grade('不知道','1','short_answer')['status']=='uncertain'
    assert grade('2 kg','2','numeric',expected_unit='m')['status']=='uncertain'
    assert grade('2','2','symbolic',grading_timeout=.001)['status']=='uncertain'

def test_mock():
    assert create_client(Settings()).test_connection()['mode']=='mock'
    assert MockLLMClient().ask('解释牛顿定律')['error'] is None

def test_timeout_fallback():
    count=[]
    def fail(request):count.append(1);raise httpx.ReadTimeout('timeout')
    c=OfficialGenAIClient(Settings(api_key='test-placeholder',base_url='https://example.test/v1',model='test',max_retries=1),transport=httpx.MockTransport(fail),sleep=lambda _:None)
    result=c.ask('不含学习记录的测试问题')
    assert result['mode']=='mock' and result['error'];assert len(count)==2
    assert 'test-placeholder' not in str(result)

def test_online_compatible_response():
    def respond(request):return httpx.Response(200,json={'id':'test','object':'chat.completion','created':0,'model':'test','choices':[{'index':0,'message':{'role':'assistant','content':'连接成功'},'finish_reason':'stop'}]})
    c=OfficialGenAIClient(Settings(api_key='test-placeholder',base_url='https://example.test/v1',model='test'),transport=httpx.MockTransport(respond))
    assert c.test_connection()['mode']=='online'
