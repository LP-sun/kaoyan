"""LLM chooses a bounded canonical exercise; arbitrary LLM statements are rejected."""
import json
from .generation import generate, SUPPORTED_MODELS

MODEL_TOPICS={'newton':'PHY-MECH-DYN-001','born':'PHY-QM-SPIN-001','torque':'PHY-MECH-ROT-TORQUE',
              'angular_acceleration':'PHY-MECH-ROT-002','normalization':'PHY-QM-WF-001',
              'rope_no_slip':'PHY-MECH-ROT-NOSLIP','pulley':'PHY-MECH-ROT-PULLEY'}


def generate_candidate(client, topic_id, allowed_models=None, variant=0, context=None):
    allowed=tuple(allowed_models or SUPPORTED_MODELS)
    if not allowed or any(model not in SUPPORTED_MODELS for model in allowed):
        raise ValueError('unsupported allowed model')
    evidence=[]
    for attempt in range(2):
        try:
            response=client.ask(json.dumps({'topic_id':topic_id,'allowed_models':allowed,'variant':variant,
                'learning_context':context or {}},ensure_ascii=False)[:5800],
                system='只输出 JSON 对象，键仅为 model 和 variant。model 必须来自 allowed_models；variant 为 0 到 1000 的整数。不要输出题面、答案或解析。')
            if response.get('mode')!='online' or response.get('fallback_text'):
                known={'PermissionDeniedError','APITimeoutError','AuthenticationError','APIConnectionError',
                    'NotFoundError','RateLimitError','ValueError','input_limit'}
                category=response.get('error') if response.get('error') in known else 'model_unavailable'
                evidence.append({'status':'needs_review','error':category})
                break
            text=response.get('text','')
            if len(text)>1000: raise ValueError('oversized proposal')
            proposal=json.loads(text)
            if not isinstance(proposal,dict) or set(proposal)!={'model','variant'}:
                raise ValueError('invalid proposal schema')
            if proposal['model'] not in allowed or type(proposal['variant']) is not int or not 0<=proposal['variant']<=1000:
                raise ValueError('invalid proposal bounds')
            record=generate(proposal['model'],topic_id,proposal['variant'])
            evidence.append({'status':record['generation']['status'],'proposal':proposal})
            record['generation']['proposal_evidence']=evidence
            record['generation']['proposal_source']='llm_selection'
            record['generation']['model_id']=str(response.get('model') or 'unspecified')[:100]
            # Only metadata; no untrusted response text or secrets are retained.
            return record
        except (ValueError,TypeError,KeyError):
            evidence.append({'status':'rejected','error':'invalid_proposal'})
        except Exception:
            evidence.append({'status':'needs_review','error':'model_call_failed'})
            break
    record=generate(allowed[0],topic_id,variant)
    record['generation']['proposal_evidence']=evidence
    record['generation']['proposal_source']='local_fallback'
    return record
