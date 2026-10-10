"""统一的时间来源。

全项目只用这里的时间函数，不使用 `datetime.utcnow()`：
后者在 Python 3.12 已弃用，且返回 naive 时间，序列化时容易被误读为本地时间。
"""
from datetime import datetime, timezone


def utcnow():
    """当前 UTC 时间（timezone-aware）。"""
    return datetime.now(timezone.utc)


def naive_utcnow():
    """写入 SQLite DateTime 列用的 naive UTC 时间（列不保存时区）。"""
    return utcnow().replace(tzinfo=None)


def to_iso(value):
    """把数据库里的 naive UTC 时间转成带 Z 的 ISO 字符串，供界面显示。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()
