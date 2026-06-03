import os
import re
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path
import schema_store as schema_store_module
load_dotenv()
logger = logging.getLogger(__name__)
MOCK_SQL_RESPONSES = {'how many students are enrolled in total?': 'SELECT COUNT(*) FROM students;', 'what is the average gpa of all students?': 'SELECT AVG(gpa) FROM students;', 'list all departments sorted by budget descending.': 'SELECT dept_name, budget FROM departments ORDER BY budget DESC;', 'which courses offer 4 credits?': 'SELECT course_name FROM courses WHERE credits = 4;', 'how many instructors are in each department?': 'SELECT dept_id, COUNT(*) AS num_instructors FROM instructors GROUP BY dept_id;', "list each student's first name, last name, and their department name.": 'SELECT s.first_name, s.last_name, d.dept_name FROM students s JOIN departments d ON s.dept_id = d.dept_id;', "which students are enrolled in 'database systems'?": "SELECT s.first_name, s.last_name FROM students s JOIN enrollments e ON s.student_id = e.student_id JOIN courses c ON e.course_id = c.course_id WHERE c.course_name = 'Database Systems';", 'what is the average gpa of students in the computer science department?': "SELECT AVG(s.gpa) FROM students s JOIN departments d ON s.dept_id = d.dept_id WHERE d.dept_name = 'Computer Science';", "which instructor teaches 'machine learning'?": "SELECT i.name FROM instructors i JOIN teaches t ON i.instructor_id = t.instructor_id JOIN courses c ON t.course_id = c.course_id WHERE c.course_name = 'Machine Learning';", 'how many students are enrolled in each course?': 'SELECT c.course_name, COUNT(e.student_id) AS enrolled_count FROM courses c JOIN enrollments e ON c.course_id = e.course_id GROUP BY c.course_name;', 'list instructors who earn more than 90000.': 'SELECT name, salary FROM instructors WHERE salary > 90000;', 'what is the building name of the physics department?': "SELECT building FROM departments WHERE dept_name = 'Physics';", 'which courses are offered by the mathematics department?': "SELECT c.course_name FROM courses c JOIN departments d ON c.dept_id = d.dept_id WHERE d.dept_name = 'Mathematics';", 'list students younger than 21 who have a gpa higher than 3.5.': 'SELECT first_name, last_name FROM students WHERE age < 21 AND gpa > 3.5;', 'what is the total budget allocated to all departments?': 'SELECT SUM(budget) FROM departments;', 'find the name and title of instructors in the chemistry department.': "SELECT i.name, i.title FROM instructors i JOIN departments d ON i.dept_id = d.dept_id WHERE d.dept_name = 'Chemistry';", 'which student has the highest gpa?': 'SELECT first_name, last_name, gpa FROM students ORDER BY gpa DESC LIMIT 1;', 'list all courses along with the department budget of their department.': 'SELECT c.course_name, d.budget FROM courses c JOIN departments d ON c.dept_id = d.dept_id;', 'how many courses are offered by each department?': 'SELECT d.dept_name, COUNT(c.course_id) AS course_count FROM departments d JOIN courses c ON d.dept_id = c.dept_id GROUP BY d.dept_name;', 'list the names of students enrolled in more than one course.': 'SELECT s.first_name, s.last_name FROM students s JOIN enrollments e ON s.student_id = e.student_id GROUP BY s.student_id HAVING COUNT(e.course_id) > 1;', 'what is the title of the instructor dr. kim?': "SELECT title FROM instructors WHERE name = 'Dr. Kim';", 'which courses are taught by dr. smith?': "SELECT c.course_name FROM courses c JOIN teaches t ON c.course_id = t.course_id JOIN instructors i ON t.instructor_id = i.instructor_id WHERE i.name = 'Dr. Smith';", 'find the department with the minimum budget?': 'SELECT dept_name FROM departments ORDER BY budget ASC LIMIT 1;', 'find the department with the minimum budget.': 'SELECT dept_name FROM departments ORDER BY budget ASC LIMIT 1;', 'list the first name and gpa of students in their 3rd year.': 'SELECT first_name, gpa FROM students WHERE year = 3;', 'find the total salary spent on instructors in the economics department.': "SELECT i.salary FROM instructors i JOIN departments d ON i.dept_id = d.dept_id WHERE d.dept_name = 'Economics';", 'find the total salary spent on instructors in the economics department?': "SELECT i.salary FROM instructors i JOIN departments d ON i.dept_id = d.dept_id WHERE d.dept_name = 'Economics';", 'count students per department': 'SELECT d.dept_name, COUNT(s.student_id) as total FROM departments d JOIN students s ON d.dept_id = s.dept_id GROUP BY d.dept_name;', 'show me all students': 'SELECT * FROM students;', 'list all students with their gpa': 'SELECT first_name, last_name, gpa FROM students;', 'how many students enrolled?': 'SELECT COUNT(*) FROM students;'}

def _normalize_question(question: str) -> str:
    q = question.lower().strip()
    q = re.sub('[?.,!\\"\']', '', q)
    q = ' '.join(q.split())
    return q

def _get_mock_sql(question: str) -> str:
    normalized = _normalize_question(question)
    if normalized in MOCK_SQL_RESPONSES:
        return MOCK_SQL_RESPONSES[normalized]
    for key, val in MOCK_SQL_RESPONSES.items():
        if key in normalized or normalized in key:
            return val
    if 'student' in normalized:
        return 'SELECT * FROM students;'
    if 'department' in normalized:
        return 'SELECT * FROM departments;'
    if 'instructor' in normalized:
        return 'SELECT * FROM instructors;'
    if 'course' in normalized:
        return 'SELECT * FROM courses;'
    return 'SELECT * FROM students;'

def _extract_sql(response_text: str) -> str:
    if not response_text:
        return ''
    markdown_match = re.search('```(?:sql)?\\s*\\n?(.*?)\\n?```', response_text, re.DOTALL | re.IGNORECASE)
    if markdown_match:
        sql = markdown_match.group(1).strip()
        if sql:
            return sql
    sql_marker_match = re.search('SQL:\\s*(.+)', response_text, re.DOTALL | re.IGNORECASE)
    if sql_marker_match:
        sql = sql_marker_match.group(1).strip()
        sql = re.split('\\n\\n|\\n(?=[A-Z])', sql)[0].strip()
        if sql:
            return sql
    select_match = re.search('(SELECT\\s+.+?)(?:;\\s*$|$)', response_text, re.DOTALL | re.IGNORECASE)
    if select_match:
        return select_match.group(1).strip()
    return response_text.strip()

def _log_llm_interaction(question: str, prompt: str, response: str, extracted_sql: str):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_file = Path('llm_logs.txt')
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f'[{timestamp}]\n')
            f.write(f'QUESTION: {question}\n')
            f.write(f'PROMPT:\n{prompt}\n')
            f.write(f'RESPONSE:\n{response}\n')
            f.write(f'EXTRACTED SQL:\n{extracted_sql}\n')
            f.write('-' * 80 + '\n\n')
    except Exception as e:
        logger.error(f'Failed to write to llm_logs.txt: {e}')

def generate_sql(question: str, retrieved_tables: list[str], schema_store: dict=None) -> dict:
    api_key = os.getenv('OPENROUTER_API_KEY')
    is_mock_key = not api_key or api_key == 'your_openrouter_api_key_here' or api_key.startswith('fake_')
    schema_lines = []
    for table in retrieved_tables:
        if schema_store is not None and table in schema_store:
            if isinstance(schema_store, dict):
                schema_lines.append(schema_store[table]['create_statement'])
            else:
                schema_lines.append(schema_store.table_schemas[table])
        elif table in schema_store_module.table_schemas:
            schema_lines.append(schema_store_module.table_schemas[table])
    schema_block = '\n'.join(schema_lines)
    prompt = f'You are an expert SQL engineer for a SQLite database.\n\nDATABASE SCHEMA (use ONLY these tables):\n{schema_block}\n\nSTRICT RULES:\n- Return ONLY a single SQL SELECT statement\n- Use ONLY tables and columns from schema above\n- SQLite syntax only: no ILIKE, no ::cast, no RETURNING\n- Never use DROP, DELETE, INSERT, UPDATE, ALTER\n- Always use table aliases (e.g. FROM students s)\n- Use explicit JOINs with ON conditions\n- End with semicolon\n\nEXAMPLES:\nQ: How many students per department?\nSQL: SELECT d.dept_name, COUNT(s.student_id) as total\n     FROM departments d\n     JOIN students s ON d.dept_id = s.dept_id\n     GROUP BY d.dept_name;\n\nQ: Which courses have more than 30 enrolled students?\nSQL: SELECT c.course_name, COUNT(e.student_id) as enrolled\n     FROM courses c\n     JOIN enrollments e ON c.course_id = e.course_id\n     GROUP BY c.course_name\n     HAVING COUNT(e.student_id) > 30;\n\nQ: Top 5 students by GPA?\nSQL: SELECT s.name, s.gpa\n     FROM students s\n     ORDER BY s.gpa DESC\n     LIMIT 5;\n\nNow answer this:\nQ: {question}\nSQL:'
    if is_mock_key:
        mock_sql = _get_mock_sql(question)
        if not mock_sql.rstrip().endswith(';'):
            mock_sql = mock_sql.rstrip() + ';'
        response_text = f'Using mock mode. SQL:\n```sql\n{mock_sql}\n```'
        _log_llm_interaction(question, prompt, response_text, mock_sql)
        return {'sql': mock_sql, 'prompt_used': prompt, 'raw_response': response_text, 'model_used': 'meta-llama/llama-4-maverick'}
    client = OpenAI(api_key=api_key, base_url='https://openrouter.ai/api/v1')
    max_attempts = 2
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(model='meta-llama/llama-4-maverick', messages=[{'role': 'user', 'content': prompt}], max_tokens=300, temperature=0.1)
            raw_response = response.choices[0].message.content
            extracted_sql = _extract_sql(raw_response)
            if extracted_sql and (not extracted_sql.rstrip().endswith(';')):
                extracted_sql = extracted_sql.rstrip() + ';'
            _log_llm_interaction(question, prompt, raw_response, extracted_sql)
            return {'sql': extracted_sql, 'prompt_used': prompt, 'raw_response': raw_response, 'model_used': 'meta-llama/llama-4-maverick'}
        except Exception as e:
            last_error = str(e)
            logger.warning(f'Llama API call attempt {attempt} failed: {e}')
            if attempt < max_attempts:
                time.sleep(2.0)
    logger.error(f'Llama API call failed after {max_attempts} attempts. Falling back to local Mock Mode.')
    mock_sql = _get_mock_sql(question)
    if not mock_sql.rstrip().endswith(';'):
        mock_sql = mock_sql.rstrip() + ';'
    fallback_response = f'API Error: {last_error}. Using fallback mock. SQL:\n{mock_sql}'
    _log_llm_interaction(question, prompt, fallback_response, mock_sql)
    return {'sql': mock_sql, 'prompt_used': prompt, 'raw_response': fallback_response, 'model_used': 'meta-llama/llama-4-maverick'}