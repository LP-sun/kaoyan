from dataclasses import dataclass, replace, field
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def _parse_models(primary, fallbacks):
    """把 `GENAI_MODEL` 与 `GENAI_MODEL_FALLBACKS` 解析成有序、去重的模型链。

    降级链的第一项始终是主模型。空项与重复项会被丢掉，
    避免把「配错了」变成「多打几次无效请求」。
    """
    chain = []
    for candidate in [primary] + str(fallbacks or '').replace(';', ',').split(','):
        name = (candidate or '').strip()
        if name and name not in chain:
            chain.append(name)
    return tuple(chain)


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default='', repr=False)
    base_url: str = ''
    model: str = ''
    timeout: float = 60
    max_retries: int = 2
    mock_mode: bool = False
    model_fallbacks: tuple = ()

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / '.env')
        return cls(os.getenv('GENAI_API_KEY',''),os.getenv('GENAI_BASE_URL',''),os.getenv('GENAI_MODEL',''),
                   float(os.getenv('GENAI_TIMEOUT','60')),int(os.getenv('GENAI_MAX_RETRIES','2')),
                   os.getenv('APP_MOCK_MODE','false').lower()=='true',
                   _parse_models(os.getenv('GENAI_MODEL',''), os.getenv('GENAI_MODEL_FALLBACKS',''))[1:])

    @property
    def models(self):
        """尝试顺序：主模型在前，其后是去重后的降级模型。"""
        return _parse_models(self.model, ','.join(self.model_fallbacks))

    @property
    def effective_mock(self):
        return self.mock_mode or not all((self.api_key,self.base_url,self.model))

    def with_parameters(self,base_url,model,timeout=60,max_retries=2,mock_mode=False):
        return replace(self,base_url=base_url.strip(),model=model.strip(),timeout=max(1,min(120,float(timeout))),
                       max_retries=max(0,min(3,int(max_retries))),mock_mode=bool(mock_mode))

