from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class QuestionInput(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str = Field(min_length=1, max_length=100)
    subject: str
    topic_ids: list[str] = Field(min_length=1)
    difficulty: int = Field(ge=1, le=5)
    question_type: Literal['single_choice','multiple_choice','numeric','symbolic','short_answer','numeric_calculation','symbolic_expression','short','derivation']
    stem: str = Field(min_length=1)
    options: list[str] = Field(default_factory=list)
    correct_answer: Any
    solution: str = Field(min_length=1)
    source_type: Literal['official_exam','textbook','original','ai_generated']
    source_reference: Any = None
    verified: bool = False
    @model_validator(mode='after')
    def check_choice(self):
        if self.question_type in ('single_choice','multiple_choice'):
            if len(self.options) < 2:
                raise ValueError('选择题至少两个选项')
            values = self.correct_answer if isinstance(self.correct_answer,list) else [self.correct_answer]
            if any(str(v) not in [chr(65+i) for i in range(len(self.options))] for v in values):
                raise ValueError('答案必须使用对应选项字母')
        return self

def validate_question(data):
    return QuestionInput.model_validate(data).model_dump()
