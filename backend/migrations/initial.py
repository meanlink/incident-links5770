from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models  # noqa: F401 注册全部模型

# 增量接入引入的可空列：对已存在的旧库做幂等补齐，新库由 create_all 直接建出。
_ADDED_COLUMNS = {
    'datasets': [
        ('root_id', 'INTEGER'),
        ('parent_id', 'INTEGER'),
        ('effective_records', 'JSON'),
        ('effective_checksum', 'VARCHAR(64)'),
        ('last_ingest_stats', 'JSON'),
    ],
}


def _backfill_columns():
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {col['name'] for col in inspector.get_columns(table)}
            for name, col_type in columns:
                if name not in present:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {col_type}'))


def migrate():
    Base.metadata.create_all(engine)
    _backfill_columns()


if __name__ == '__main__':
    migrate()
