"""可重复执行的迁移机制。

设计：
- `MIGRATIONS` 是 (version, description, callable) 的有序列表，只允许追加，不修改历史项；
- `schema_migrations(version INTEGER PRIMARY KEY)` 记录已应用版本，因此重复启动是幂等的；
- 每个迁移在单独事务中执行；失败回滚并抛出，不会留下半套结构；
- 首个迁移用 `create_all` 建表，后续结构性变更以“检查后修改”的方式写成幂等语句，
  这样旧库升级和新库初始化走同一条代码路径。

不使用 Alembic：本项目单文件 SQLite、单用户本地运行，显式列表比重型迁移框架更容易审计。
等价性说明见 docs/ARCHITECTURE.md。
"""
from datetime import datetime
from sqlalchemy import inspect, text

from ...clock import naive_utcnow
from ..models import Base


def _column_names(connection, table):
    return {column['name'] for column in inspect(connection).get_columns(table)}


def _migration_001_create_schema(connection):
    """建立全部业务表（幂等）。"""
    Base.metadata.create_all(connection)


def _migration_002_web_sessions(connection):
    """为例外情况补齐 exam_sessions.status 默认值（幂等）。"""
    if 'exam_sessions' in inspect(connection).get_table_names():
        connection.execute(text(
            "UPDATE exam_sessions SET status='active' WHERE status IS NULL OR status=''"))


def _migration_003_attempt_created_at(connection):
    """保证历史 attempts 都有 created_at，避免 dashboard 统计出现 NULL 比较。"""
    if 'attempts' in inspect(connection).get_table_names():
        connection.execute(text(
            "UPDATE attempts SET created_at=:now WHERE created_at IS NULL"),
            {'now': naive_utcnow().isoformat(sep=' ')})


MIGRATIONS = (
    (1, '建立 users/topics/questions/sessions/attempts/mastery/review/llm_usage 等基础表', _migration_001_create_schema),
    (2, '规范化 exam_sessions.status', _migration_002_web_sessions),
    (3, '回填 attempts.created_at', _migration_003_attempt_created_at),
)


def current_version(engine):
    with engine.connect() as connection:
        if 'schema_migrations' not in inspect(connection).get_table_names():
            return 0
        row = connection.execute(text('SELECT max(version) FROM schema_migrations')).scalar()
    return int(row or 0)


def run_migrations(engine):
    """应用所有未执行的迁移，返回已应用到的版本号。"""
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)'))
    applied = set()
    with engine.connect() as connection:
        applied = {int(row[0]) for row in connection.execute(text('SELECT version FROM schema_migrations'))}

    for version, description, operation in sorted(MIGRATIONS, key=lambda item: item[0]):
        if version in applied:
            continue
        with engine.begin() as connection:
            operation(connection)
            connection.execute(text('INSERT OR IGNORE INTO schema_migrations (version) VALUES (:v)'),
                               {'v': version})
    return current_version(engine)
