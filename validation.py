import sqlglot
import sqlglot.errors

def validate_sql(sql: str) -> dict:
    if sql is None or not str(sql).strip():
        return {'is_valid': False, 'errors': ['SQL is empty']}
    sql_str = str(sql).strip()
    if not sql_str.upper().startswith('SELECT'):
        return {'is_valid': False, 'errors': ['Only SELECT statements allowed']}
    dangerous_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER', 'TRUNCATE', 'CREATE']
    sql_upper = sql_str.upper()
    for kw in dangerous_keywords:
        import re
        if re.search('\\b' + re.escape(kw) + '\\b', sql_upper):
            return {'is_valid': False, 'errors': [f"Mutation keyword '{kw}' detected. Only SELECT allowed."]}
    try:
        sqlglot.parse_one(sql_str, dialect='sqlite')
        return {'is_valid': True, 'errors': None}
    except sqlglot.errors.ParseError as e:
        return {'is_valid': False, 'errors': [str(e)]}
    except Exception as e:
        return {'is_valid': False, 'errors': [f'Parse error: {str(e)}']}