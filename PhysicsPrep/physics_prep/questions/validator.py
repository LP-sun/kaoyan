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
    content_status: Literal['extracted','normalized','statement_verified','solution_draft','solution_checked','practice_ready','needs_review','blocked','out_of_scope','duplicate_candidate'] = 'normalized'
    content_priority: int = Field(default=0, ge=0, le=100)
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
    result = QuestionInput.model_validate(data).model_dump()
    if result['source_type'] == 'ai_generated' and result['content_status'] == 'practice_ready':
        result['content_status'] = 'solution_checked'
    if result['verified'] and result['source_type'] != 'ai_generated' and result['content_status'] == 'normalized':
        result['content_status'] = 'practice_ready'
    return result
