import sqlite3
from pathlib import Path

def execute_sql(sql: str, db_path: str='database.db') -> dict:
    conn = None
    try:
        if not sql or not str(sql).strip():
            return {'columns': None, 'rows': None, 'row_count': 0, 'error': 'SQL query is empty'}
        sql_str = str(sql).strip()
        if not Path(db_path).exists():
            return {'columns': None, 'rows': None, 'row_count': 0, 'error': f"Database file not found at '{db_path}'"}
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql_str)
        columns = None
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
        raw_rows = cursor.fetchmany(100)
        rows = [list(row) for row in raw_rows]
        return {'columns': columns, 'rows': rows, 'row_count': len(rows), 'error': None}
    except sqlite3.Error as e:
        return {'columns': None, 'rows': None, 'row_count': 0, 'error': str(e)}
    except Exception as e:
        return {'columns': None, 'rows': None, 'row_count': 0, 'error': f'Unexpected error: {str(e)}'}
    finally:
        if conn is not None:
            conn.close()