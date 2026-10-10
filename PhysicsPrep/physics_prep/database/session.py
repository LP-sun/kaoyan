from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from ..clock import naive_utcnow, to_iso, utcnow  # noqa: F401  (re-exported for callers)
from .migrations import current_version, run_migrations
from .models import Base, User

SQLITE_CONNECT_ARGS = {'check_same_thread': False, 'timeout': 30}


def initialize_database(path):
    """打开（必要时创建）数据库，跑完迁移并保证存在本地用户。

    SQLite 配置面向“单用户本地应用但界面可能并发调用”的场景：
    WAL 允许读写并行，busy_timeout 让并发写等待而不是立刻报错，
    foreign_keys 打开以保证知识树与题库的引用完整性。
    """
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine('sqlite:///' + path.as_posix(), connect_args=SQLITE_CONNECT_ARGS)

    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA busy_timeout=30000')
        connection.execute('PRAGMA synchronous=NORMAL')

    Base.metadata.create_all(engine)
    run_migrations(engine)

    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        if not session.get(User, 'local'):
            session.add(User(id='local'))
    return engine, factory


__all__ = ['initialize_database', 'current_version', 'run_migrations',
           'Base', 'User', 'utcnow', 'naive_utcnow', 'to_iso']
