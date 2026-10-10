"""在两个 PhysicsPrep SQLite 库之间迁移学习记录（会话/作答/掌握度/复习计划/标记/用量）。

用法：
    python tools/migrate_records.py --source data/ui-check/study.sqlite3 --target data/physics_prep.sqlite3

只复制学习记录表，不触碰题库与知识树（目标库应已由应用完成种子导入）。
主键已存在的行跳过，不覆盖目标库既有记录；整体在一个 IMMEDIATE 事务中执行。
"""
import argparse
import sqlite3
from pathlib import Path

TABLES = ['exam_sessions', 'attempts', 'mastery_records', 'review_schedule',
          'question_marks', 'llm_usage']


def columns_of(con, table):
    return [row[1] for row in con.execute(f'PRAGMA table_info({table})')]


def primary_key_of(con, table):
    return [row[1] for row in con.execute(f'PRAGMA table_info({table})') if row[5] > 0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='来源库（只读打开）')
    parser.add_argument('--target', required=True, help='目标库（写入）')
    args = parser.parse_args()
    source_path, target_path = Path(args.source), Path(args.target)
    if not source_path.is_file():
        raise SystemExit(f'来源库不存在：{source_path}')
    if not target_path.is_file():
        raise SystemExit(f'目标库不存在：{target_path}')

    source = sqlite3.connect(f'file:{source_path.as_posix()}?mode=ro', uri=True)
    target = sqlite3.connect(target_path, isolation_level=None)
    target.execute('PRAGMA busy_timeout=30000')
    total = 0
    try:
        target.execute('BEGIN IMMEDIATE')
        for table in TABLES:
            known = target.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not known:
                print(f'- {table}: 目标库无此表，跳过')
                continue
            shared = [c for c in columns_of(target, table) if c in set(columns_of(source, table))]
            pk = primary_key_of(target, table)
            rows = source.execute(f'SELECT {",".join(shared)} FROM {table}').fetchall()
            copied = 0
            for row in rows:
                if pk:
                    values = dict(zip(shared, row))
                    where = ' AND '.join(f'{k}=?' for k in pk)
                    if target.execute(
                            f'SELECT 1 FROM {table} WHERE {where}', [values[k] for k in pk]).fetchone():
                        continue
                target.execute(
                    f'INSERT INTO {table} ({",".join(shared)}) VALUES ({",".join("?" * len(shared))})', row)
                copied += 1
            total += copied
            print(f'- {table}: 来源 {len(rows)} 行，迁移 {copied} 行')
        target.execute('COMMIT')
    except Exception:
        target.execute('ROLLBACK')
        raise
    finally:
        source.close()
        target.close()
    print(f'共迁移 {total} 行 → {target_path}')


if __name__ == '__main__':
    main()
