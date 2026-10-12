from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from ..clock import naive_utcnow as _now_naive


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, default='本地学习者')


class Topic(Base):
    __tablename__ = 'topics'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('topics.id'), nullable=True)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    source_references: Mapped[list] = mapped_column(JSON, default=list)


class TopicPrerequisite(Base):
    __tablename__ = 'topic_prerequisites'
    topic_id: Mapped[str] = mapped_column(ForeignKey('topics.id'), primary_key=True)
    prerequisite_id: Mapped[str] = mapped_column(ForeignKey('topics.id'), primary_key=True)


class Question(Base):
    __tablename__ = 'questions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    subject: Mapped[str] = mapped_column(String, index=True)
    difficulty: Mapped[int] = mapped_column(Integer)
    question_type: Mapped[str] = mapped_column(String)
    verified: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JSON)


class QuestionTopic(Base):
    __tablename__ = 'question_topics'
    question_id: Mapped[str] = mapped_column(ForeignKey('questions.id'), primary_key=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey('topics.id'), primary_key=True)


class ExamSession(Base):
    __tablename__ = 'exam_sessions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    chapter: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now_naive)
    current_question_id: Mapped[str | None] = mapped_column(String, nullable=True)
    current_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default='active')


class Attempt(Base):
    __tablename__ = 'attempts'
    # token 唯一约束是“重复点击提交只产生一条记录”的最终保证。
    __table_args__ = (UniqueConstraint('user_id', 'token'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    session_id: Mapped[str] = mapped_column(ForeignKey('exam_sessions.id'))
    question_id: Mapped[str] = mapped_column(String)
    token: Mapped[str] = mapped_column(String)
    answer: Mapped[object] = mapped_column(JSON)
    # snapshot 保存作答当时的题目快照，题目之后被修改也不影响历史记录的可解释性。
    snapshot: Mapped[dict] = mapped_column(JSON)
    feedback: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now_naive)


class MasteryRecord(Base):
    __tablename__ = 'mastery_records'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey('topics.id'), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    recent: Mapped[list] = mapped_column(JSON, default=list)
    last_practiced: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReviewSchedule(Base):
    __tablename__ = 'review_schedule'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey('topics.id'), primary_key=True)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    interval_days: Mapped[int] = mapped_column(Integer, default=1)


class LLMUsage(Base):
    __tablename__ = 'llm_usage'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    model: Mapped[str] = mapped_column(String)
    operation: Mapped[str] = mapped_column(String)
    success: Mapped[int] = mapped_column(Integer)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now_naive)


class QuestionMark(Base):
    __tablename__ = 'question_marks'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    question_id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now_naive)


class TutorTurn(Base):
    __tablename__ = 'tutor_turns'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('exam_sessions.id'))
    question_id: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now_naive)
