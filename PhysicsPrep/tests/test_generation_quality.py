import copy
import pytest
from physics_prep.questions.generation import generate, SUPPORTED_MODELS
from physics_prep.questions.generated_validation import validate_generated
from physics_prep.questions.candidates import generate_candidate

@pytest.mark.parametrize('model',SUPPORTED_MODELS)
def test_independent_validation(model):
    for variant in (0,1,12,1000):
        q=generate(model,'test',variant)
        assert q['validation']['passed'] and q['machine_validated']
        assert not q['human_verified'] and not q['verified']
        assert generate(model,'test',variant)['id']==q['id']
        altered=copy.deepcopy(q); altered['correct_answer']='999'
        assert validate_generated(altered)['status']=='rejected'
        altered=copy.deepcopy(q); altered['stem']+=' extra force'
        assert not validate_generated(altered)['passed']
        altered=copy.deepcopy(q); altered['generation']['parameters'][next(iter(altered['generation']['parameters']))]=0
        assert not validate_generated(altered)['passed']

@pytest.mark.parametrize('variant',[-1,1001,True,1.5,'1'])
def test_variants_are_bounded(variant):
    with pytest.raises(ValueError): generate('newton','test',variant)

class Client:
    def __init__(self,text,mode='online'): self.text=text; self.mode=mode; self.calls=0
    def ask(self,*args,**kwargs):
        self.calls+=1
        return {'text':self.text,'mode':self.mode}

def test_llm_can_only_select_canonical_parameters():
    client=Client('{"model":"torque","variant":2}')
    q=generate_candidate(client,'test',['torque'])
    assert q['machine_validated'] and client.calls==1
    assert q['generation']['proposal_source']=='llm_selection'
    assert q['stem']==generate('torque','test',2)['stem']

def test_arbitrary_llm_answer_rejected_and_bounded():
    client=Client('{"model":"torque","variant":2,"correct_answer":"wrong"}')
    q=generate_candidate(client,'test',['torque'])
    assert client.calls==2
    assert q['generation']['proposal_source']=='local_fallback'
    assert all(x['status']=='rejected' for x in q['generation']['proposal_evidence'])

def test_mock_failure_does_not_claim_online_generation():
    client=Client('secret response','mock')
    q=generate_candidate(client,'test',['normalization'])
    assert client.calls==1 and q['machine_validated']
    assert 'secret' not in str(q)
    assert q['generation']['proposal_source']=='local_fallback'


def test_torque_verification_uses_different_wording():
    first=generate('torque','t',0); second=generate('torque','t',1)
    assert first['stem'] != second['stem']
    assert '切向' in first['stem'] and '作用线' in second['stem']
    assert first['machine_validated'] and second['machine_validated']
