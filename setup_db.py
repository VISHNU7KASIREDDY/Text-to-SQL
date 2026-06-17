import json
import logging
import sqlite3
from pathlib import Path
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
DB_PATH = Path('database.db')
SCHEMA_CACHE_PATH = Path('schema_cache.json')
DB_ID = 'university'
TABLES_SCHEMA = {'departments': [('dept_id', 'INTEGER'), ('dept_name', 'TEXT'), ('building', 'TEXT'), ('budget', 'REAL')], 'students': [('student_id', 'INTEGER'), ('first_name', 'TEXT'), ('last_name', 'TEXT'), ('age', 'INTEGER'), ('gpa', 'REAL'), ('dept_id', 'INTEGER'), ('email', 'TEXT'), ('major', 'TEXT'), ('year', 'INTEGER')], 'instructors': [('instructor_id', 'INTEGER'), ('name', 'TEXT'), ('dept_id', 'INTEGER'), ('salary', 'REAL'), ('title', 'TEXT')], 'courses': [('course_id', 'INTEGER'), ('course_name', 'TEXT'), ('dept_id', 'INTEGER'), ('credits', 'INTEGER'), ('description', 'TEXT')], 'enrollments': [('enrollment_id', 'INTEGER'), ('student_id', 'INTEGER'), ('course_id', 'INTEGER'), ('grade', 'TEXT'), ('semester', 'TEXT')], 'teaches': [('teaches_id', 'INTEGER'), ('instructor_id', 'INTEGER'), ('course_id', 'INTEGER'), ('semester', 'TEXT'), ('year', 'INTEGER')]}
SEED_DATA = {'departments': [{'dept_id': 1, 'dept_name': 'Computer Science', 'building': 'Tech Hall', 'budget': 850000.0}, {'dept_id': 2, 'dept_name': 'Mathematics', 'building': 'Euler Hall', 'budget': 450000.0}, {'dept_id': 3, 'dept_name': 'Physics', 'building': 'Einstein Center', 'budget': 600000.0}, {'dept_id': 4, 'dept_name': 'Chemistry', 'building': 'Curie Lab', 'budget': 550000.0}, {'dept_id': 5, 'dept_name': 'Biology', 'building': 'Darwin Hall', 'budget': 500000.0}, {'dept_id': 6, 'dept_name': 'Economics', 'building': 'Keynes Building', 'budget': 400000.0}, {'dept_id': 7, 'dept_name': 'English', 'building': 'Shakespeare Hall', 'budget': 250000.0}, {'dept_id': 8, 'dept_name': 'History', 'building': 'Herodotus Hall', 'budget': 200000.0}, {'dept_id': 9, 'dept_name': 'Psychology', 'building': 'Freud Hall', 'budget': 350000.0}, {'dept_id': 10, 'dept_name': 'Philosophy', 'building': 'Socrates Hall', 'budget': 150000.0}, {'dept_id': 11, 'dept_name': 'Civil Engineering', 'building': 'Smeaton Tower', 'budget': 700000.0}, {'dept_id': 12, 'dept_name': 'Mechanical Engineering', 'building': 'Watt Lab', 'budget': 750000.0}, {'dept_id': 13, 'dept_name': 'Electrical Engineering', 'building': 'Tesla Center', 'budget': 800000.0}, {'dept_id': 14, 'dept_name': 'Political Science', 'building': 'Machiavelli Hall', 'budget': 300000.0}, {'dept_id': 15, 'dept_name': 'Sociology', 'building': 'Weber Building', 'budget': 220000.0}], 'students': [{'student_id': 1, 'first_name': 'Alice', 'last_name': 'Johnson', 'age': 20, 'gpa': 3.85, 'dept_id': 1, 'email': 'alice@univ.edu', 'major': 'Computer Science', 'year': 2}, {'student_id': 2, 'first_name': 'Bob', 'last_name': 'Smith', 'age': 22, 'gpa': 3.4, 'dept_id': 2, 'email': 'bob@univ.edu', 'major': 'Mathematics', 'year': 4}, {'student_id': 3, 'first_name': 'Charlie', 'last_name': 'Brown', 'age': 19, 'gpa': 2.95, 'dept_id': 1, 'email': 'charlie@univ.edu', 'major': 'Computer Science', 'year': 1}, {'student_id': 4, 'first_name': 'Diana', 'last_name': 'Prince', 'age': 21, 'gpa': 3.9, 'dept_id': 3, 'email': 'diana@univ.edu', 'major': 'Physics', 'year': 3}, {'student_id': 5, 'first_name': 'Evan', 'last_name': 'Wright', 'age': 23, 'gpa': 3.15, 'dept_id': 6, 'email': 'evan@univ.edu', 'major': 'Economics', 'year': 4}, {'student_id': 6, 'first_name': 'Fiona', 'last_name': 'Gallagher', 'age': 20, 'gpa': 2.7, 'dept_id': 4, 'email': 'fiona@univ.edu', 'major': 'Chemistry', 'year': 2}, {'student_id': 7, 'first_name': 'George', 'last_name': 'Martin', 'age': 22, 'gpa': 3.65, 'dept_id': 7, 'email': 'george@univ.edu', 'major': 'English', 'year': 3}, {'student_id': 8, 'first_name': 'Hannah', 'last_name': 'Abbott', 'age': 21, 'gpa': 3.5, 'dept_id': 5, 'email': 'hannah@univ.edu', 'major': 'Biology', 'year': 3}, {'student_id': 9, 'first_name': 'Ian', 'last_name': 'Malcolm', 'age': 24, 'gpa': 3.98, 'dept_id': 2, 'email': 'ian@univ.edu', 'major': 'Mathematics', 'year': 5}, {'student_id': 10, 'first_name': 'Julia', 'last_name': 'Roberts', 'age': 19, 'gpa': 3.2, 'dept_id': 9, 'email': 'julia@univ.edu', 'major': 'Psychology', 'year': 1}, {'student_id': 11, 'first_name': 'Kevin', 'last_name': 'Bacon', 'age': 20, 'gpa': 3.05, 'dept_id': 13, 'email': 'kevin@univ.edu', 'major': 'Electrical Engineering', 'year': 2}, {'student_id': 12, 'first_name': 'Laura', 'last_name': 'Croft', 'age': 22, 'gpa': 3.75, 'dept_id': 8, 'email': 'laura@univ.edu', 'major': 'History', 'year': 4}, {'student_id': 13, 'first_name': 'Michael', 'last_name': 'Jordan', 'age': 21, 'gpa': 3.45, 'dept_id': 6, 'email': 'michael@univ.edu', 'major': 'Economics', 'year': 3}, {'student_id': 14, 'first_name': 'Nancy', 'last_name': 'Drew', 'age': 18, 'gpa': 4.0, 'dept_id': 14, 'email': 'nancy@univ.edu', 'major': 'Political Science', 'year': 1}, {'student_id': 15, 'first_name': 'Oscar', 'last_name': 'Wilde', 'age': 23, 'gpa': 3.3, 'dept_id': 10, 'email': 'oscar@univ.edu', 'major': 'Philosophy', 'year': 4}], 'instructors': [{'instructor_id': 1, 'name': 'Dr. Smith', 'dept_id': 1, 'salary': 95000.0, 'title': 'Professor'}, {'instructor_id': 2, 'name': 'Dr. Jones', 'dept_id': 2, 'salary': 88000.0, 'title': 'Associate Professor'}, {'instructor_id': 3, 'name': 'Dr. Lee', 'dept_id': 3, 'salary': 91000.0, 'title': 'Professor'}, {'instructor_id': 4, 'name': 'Dr. Patel', 'dept_id': 4, 'salary': 87000.0, 'title': 'Assistant Professor'}, {'instructor_id': 5, 'name': 'Dr. Nguyen', 'dept_id': 5, 'salary': 86000.0, 'title': 'Associate Professor'}, {'instructor_id': 6, 'name': 'Dr. Kim', 'dept_id': 1, 'salary': 99000.0, 'title': 'Professor'}, {'instructor_id': 7, 'name': 'Dr. Garcia', 'dept_id': 6, 'salary': 92000.0, 'title': 'Professor'}, {'instructor_id': 8, 'name': 'Dr. Miller', 'dept_id': 7, 'salary': 75000.0, 'title': 'Associate Professor'}, {'instructor_id': 9, 'name': 'Dr. Davis', 'dept_id': 9, 'salary': 82000.0, 'title': 'Assistant Professor'}, {'instructor_id': 10, 'name': 'Dr. Wilson', 'dept_id': 13, 'salary': 105000.0, 'title': 'Professor'}, {'instructor_id': 11, 'name': 'Dr. Thomas', 'dept_id': 11, 'salary': 89000.0, 'title': 'Associate Professor'}, {'instructor_id': 12, 'name': 'Dr. Taylor', 'dept_id': 12, 'salary': 93000.0, 'title': 'Professor'}, {'instructor_id': 13, 'name': 'Dr. Anderson', 'dept_id': 14, 'salary': 78000.0, 'title': 'Assistant Professor'}, {'instructor_id': 14, 'name': 'Dr. Jackson', 'dept_id': 8, 'salary': 84000.0, 'title': 'Associate Professor'}, {'instructor_id': 15, 'name': 'Dr. White', 'dept_id': 10, 'salary': 72000.0, 'title': 'Lecturer'}], 'courses': [{'course_id': 1, 'course_name': 'Database Systems', 'dept_id': 1, 'credits': 3, 'description': 'Introduction to relational databases'}, {'course_id': 2, 'course_name': 'Algorithms', 'dept_id': 1, 'credits': 4, 'description': 'Algorithm design and complexity'}, {'course_id': 3, 'course_name': 'Calculus I', 'dept_id': 2, 'credits': 4, 'description': 'Differential calculus basics'}, {'course_id': 4, 'course_name': 'Quantum Mechanics', 'dept_id': 3, 'credits': 3, 'description': 'Introduction to quantum physics'}, {'course_id': 5, 'course_name': 'Organic Chemistry', 'dept_id': 4, 'credits': 4, 'description': 'Compounds of carbon'}, {'course_id': 6, 'course_name': 'Machine Learning', 'dept_id': 1, 'credits': 3, 'description': 'Foundations of statistical learning'}, {'course_id': 7, 'course_name': 'Linear Algebra', 'dept_id': 2, 'credits': 3, 'description': 'Matrix operations and spaces'}, {'course_id': 8, 'course_name': 'Cell Biology', 'dept_id': 5, 'credits': 3, 'description': 'Cell structure and function'}, {'course_id': 9, 'course_name': 'Microeconomics', 'dept_id': 6, 'credits': 3, 'description': 'Market systems and allocation'}, {'course_id': 10, 'course_name': 'Creative Writing', 'dept_id': 7, 'credits': 3, 'description': 'Fiction and poetry workshop'}, {'course_id': 11, 'course_name': 'Ancient History', 'dept_id': 8, 'credits': 3, 'description': 'Mediterranean civilizations'}, {'course_id': 12, 'course_name': 'Cognitive Psychology', 'dept_id': 9, 'credits': 3, 'description': 'Memory and perception'}, {'course_id': 13, 'course_name': 'Intro to Ethics', 'dept_id': 10, 'credits': 3, 'description': 'Classical ethical theories'}, {'course_id': 14, 'course_name': 'Structural Analysis', 'dept_id': 11, 'credits': 4, 'description': 'Beams and truss systems'}, {'course_id': 15, 'course_name': 'Thermodynamics', 'dept_id': 12, 'credits': 3, 'description': 'Heat and energy laws'}], 'enrollments': [{'enrollment_id': 1, 'student_id': 1, 'course_id': 1, 'grade': 'A', 'semester': 'Fall 2025'}, {'enrollment_id': 2, 'student_id': 1, 'course_id': 2, 'grade': 'B+', 'semester': 'Fall 2025'}, {'enrollment_id': 3, 'student_id': 2, 'course_id': 3, 'grade': 'A-', 'semester': 'Fall 2025'}, {'enrollment_id': 4, 'student_id': 3, 'course_id': 1, 'grade': 'B', 'semester': 'Fall 2025'}, {'enrollment_id': 5, 'student_id': 4, 'course_id': 4, 'grade': 'A', 'semester': 'Spring 2026'}, {'enrollment_id': 6, 'student_id': 5, 'course_id': 9, 'grade': 'B-', 'semester': 'Fall 2025'}, {'enrollment_id': 7, 'student_id': 6, 'course_id': 5, 'grade': 'C+', 'semester': 'Spring 2026'}, {'enrollment_id': 8, 'student_id': 7, 'course_id': 10, 'grade': 'A', 'semester': 'Fall 2025'}, {'enrollment_id': 9, 'student_id': 8, 'course_id': 8, 'grade': 'A-', 'semester': 'Spring 2026'}, {'enrollment_id': 10, 'student_id': 9, 'course_id': 7, 'grade': 'A', 'semester': 'Fall 2025'}, {'enrollment_id': 11, 'student_id': 10, 'course_id': 12, 'grade': 'B+', 'semester': 'Spring 2026'}, {'enrollment_id': 12, 'student_id': 11, 'course_id': 1, 'grade': 'B', 'semester': 'Fall 2025'}, {'enrollment_id': 13, 'student_id': 12, 'course_id': 11, 'grade': 'A-', 'semester': 'Fall 2025'}, {'enrollment_id': 14, 'student_id': 13, 'course_id': 9, 'grade': 'B', 'semester': 'Fall 2025'}, {'enrollment_id': 15, 'student_id': 15, 'course_id': 13, 'grade': 'B+', 'semester': 'Spring 2026'}], 'teaches': [{'teaches_id': 1, 'instructor_id': 1, 'course_id': 1, 'semester': 'Fall 2025', 'year': 2025}, {'teaches_id': 2, 'instructor_id': 1, 'course_id': 6, 'semester': 'Spring 2026', 'year': 2026}, {'teaches_id': 3, 'instructor_id': 2, 'course_id': 3, 'semester': 'Fall 2025', 'year': 2025}, {'teaches_id': 4, 'instructor_id': 3, 'course_id': 4, 'semester': 'Spring 2026', 'year': 2026}, {'teaches_id': 5, 'instructor_id': 4, 'course_id': 5, 'semester': 'Spring 2026', 'year': 2026}, {'teaches_id': 6, 'instructor_id': 6, 'course_id': 2, 'semester': 'Fall 2025', 'year': 2025}, {'teaches_id': 7, 'instructor_id': 7, 'course_id': 9, 'semester': 'Fall 2025', 'year': 2025}, {'teaches_id': 8, 'instructor_id': 8, 'course_id': 10, 'semester': 'Fall 2025', 'year': 2025}, {'teaches_id': 9, 'instructor_id': 9, 'course_id': 12, 'semester': 'Spring 2026', 'year': 2026}, {'teaches_id': 10, 'instructor_id': 10, 'course_id': 1, 'semester': 'Fall 2025', 'year': 2025}, {'teaches_id': 11, 'instructor_id': 11, 'course_id': 14, 'semester': 'Fall 2025', 'year': 2025}, {'teaches_id': 12, 'instructor_id': 12, 'course_id': 15, 'semester': 'Spring 2026', 'year': 2026}, {'teaches_id': 13, 'instructor_id': 13, 'course_id': 13, 'semester': 'Spring 2026', 'year': 2026}, {'teaches_id': 14, 'instructor_id': 14, 'course_id': 11, 'semester': 'Fall 2025', 'year': 2025}, {'teaches_id': 15, 'instructor_id': 15, 'course_id': 13, 'semester': 'Spring 2026', 'year': 2026}]}

def _extract_beaver_schema(ds) -> tuple[dict, str]:
    """
    Extract schema and tables from BEAVER dataset.
    Returns: (tables_dict, db_id)
    """
    logger.info("Extracting schema from BEAVER dataset...")
    try:

        sample = ds['train'][0] if 'train' in ds else ds[0]
        
        if 'schema' not in sample:
            raise ValueError("BEAVER dataset missing 'schema' field")
        
        schema_data = sample['schema']
        db_id = sample.get('db_id', 'beaver_db')
        
        logger.info(f"Found database: {db_id}")
        logger.info(f"Schema structure: {schema_data}")
        
        tables = {}
        
        if isinstance(schema_data, dict):
       
            table_names = schema_data.get('table_names', [])
            column_names = schema_data.get('column_names', [])  
            column_types = schema_data.get('column_types', [])
            
            for table_idx, table_name in enumerate(table_names):
                columns = []
                for col_idx, (tbl_idx, col_name) in enumerate(column_names):
                    if tbl_idx == table_idx:
                        col_type = column_types[col_idx] if col_idx < len(column_types) else 'TEXT'
                        columns.append((col_name, col_type))
                
                if columns:
                    tables[table_name] = columns
                    logger.info(f"  Table '{table_name}': {len(columns)} columns")
        
        if not tables:
            raise ValueError("Could not extract tables from BEAVER schema")
        
        logger.info(f"Successfully extracted {len(tables)} tables from BEAVER")
        return tables, db_id
    
    except Exception as e:
        logger.error(f"Failed to extract BEAVER schema: {e}")
        raise

def build_database():
    beaver_tables = None
    beaver_db_id = None
    
    try:
        from datasets import load_dataset
        logger.info("Attempting to load 'AppliedResearch/BEAVER' from HuggingFace...")
        ds = load_dataset('AppliedResearch/BEAVER', trust_remote_code=True)
        logger.info(f'BEAVER Dataset loaded. Structure: {ds}')
        

        beaver_tables, beaver_db_id = _extract_beaver_schema(ds)
        logger.info(f"Using BEAVER database: {beaver_db_id} with {len(beaver_tables)} tables")
        
    except Exception as e:
        logger.warning(f'Could not load BEAVER dataset ({e}). Falling back to built-in schema.')
        logger.info("Visualization of expected BEAVER dataset structure:")
        logger.info("  DatasetDict(train: Dataset(features: ['db_id', 'question', 'gold_sql', 'schema'], ...))")
    

    if beaver_tables:
        tables_to_use = beaver_tables
        db_id_to_use = beaver_db_id
        logger.info(f"Using BEAVER schema: db_id='{db_id_to_use}'")
    else:
        tables_to_use = TABLES_SCHEMA
        db_id_to_use = DB_ID
        logger.info(f"Using fallback schema: db_id='{db_id_to_use}' ({len(TABLES_SCHEMA)} tables)")
    if DB_PATH.exists():
        DB_PATH.unlink()
        logger.info(f'Deleted old {DB_PATH}')
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    conn.execute('PRAGMA foreign_keys = OFF;')
    
    create_statements = {}
    tables_created = 0
    total_rows = 0
    
    for table_name, columns in tables_to_use.items():
        col_defs = ', '.join((f'`{col}` {ctype}' for col, ctype in columns))
        create_sql = f'CREATE TABLE IF NOT EXISTS `{table_name}` ({col_defs});'
        create_statements[table_name] = create_sql
        cursor.execute(create_sql)
        tables_created += 1
        
        seed_list = SEED_DATA.get(table_name, []) if db_id_to_use == DB_ID else []
        col_names = [c[0] for c in columns]
        
        for row in seed_list:
            placeholders = ', '.join(('?' for _ in col_names))
            vals = [row.get(c) for c in col_names]
            cursor.execute(f"INSERT OR IGNORE INTO `{table_name}` ({', '.join((f'`{c}`' for c in col_names))}) VALUES ({placeholders})", vals)
            total_rows += 1
        
        if seed_list:
            logger.info(f"  Inserted {len(seed_list)} rows into '{table_name}'")
        elif db_id_to_use == DB_ID:
            logger.info(f"  Created table '{table_name}' ({len(col_names)} columns)")
        else:
            logger.info(f"  Created table '{table_name}' ({len(col_names)} columns) - schema-only (BEAVER)")
    conn.commit()
    conn.close()
    
    cache = {}
    for table_name, columns in tables_to_use.items():
        cache[table_name] = {'columns': [{'name': c[0], 'type': c[1]} for c in columns], 'create_statement': create_statements[table_name]}
    
    payload = {'db_id': db_id_to_use, 'tables': cache}
    with open(SCHEMA_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    logger.info(f'Setup complete: {tables_created} tables created, {total_rows} total rows inserted')
    logger.info(f'Database ID: {db_id_to_use}')
    logger.info('schema_cache.json saved')
    logger.info('database.db created')
    print(f'✓ Setup complete: {tables_created} tables, {total_rows} rows (db_id: {db_id_to_use})')
if __name__ == '__main__':
    build_database()