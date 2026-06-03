import logging
import re
import time
from typing import Optional
import numpy as np
from execution import execute_sql
from llm import generate_sql
from retrieval import retrieve_tables
from validation import validate_sql
logger = logging.getLogger(__name__)
BENCHMARK_SIZE = 25
BUILTIN_BENCHMARK_PAIRS: list[dict] = [{'question': 'How many students are enrolled in total?', 'gold_sql': 'SELECT COUNT(*) FROM students;'}, {'question': 'What is the average GPA of all students?', 'gold_sql': 'SELECT AVG(gpa) FROM students;'}, {'question': 'List all departments sorted by budget descending.', 'gold_sql': 'SELECT dept_name, budget FROM departments ORDER BY budget DESC;'}, {'question': 'Which courses offer 4 credits?', 'gold_sql': 'SELECT course_name FROM courses WHERE credits = 4;'}, {'question': 'How many instructors are in each department?', 'gold_sql': 'SELECT dept_id, COUNT(*) AS num_instructors FROM instructors GROUP BY dept_id;'}, {'question': "List each student's full name and their department name.", 'gold_sql': 'SELECT s.first_name, s.last_name, d.dept_name FROM students s JOIN departments d ON s.dept_id = d.dept_id;'}, {'question': "Which students are enrolled in 'Database Systems'?", 'gold_sql': "SELECT s.first_name, s.last_name FROM students s JOIN enrollments e ON s.student_id = e.student_id JOIN courses c ON e.course_id = c.course_id WHERE c.course_name = 'Database Systems';"}, {'question': 'What is the average GPA per department?', 'gold_sql': 'SELECT d.dept_name, AVG(s.gpa) AS avg_gpa FROM departments d JOIN students s ON d.dept_id = s.dept_id GROUP BY d.dept_name;'}, {'question': 'Which instructor teaches Machine Learning?', 'gold_sql': "SELECT i.name FROM instructors i JOIN teaches t ON i.instructor_id = t.instructor_id JOIN courses c ON t.course_id = c.course_id WHERE c.course_name = 'Machine Learning';"}, {'question': 'How many students are enrolled in each course?', 'gold_sql': 'SELECT c.course_name, COUNT(e.student_id) AS total FROM courses c JOIN enrollments e ON c.course_id = e.course_id GROUP BY c.course_name;'}, {'question': 'How many patients are admitted in total?', 'gold_sql': 'SELECT COUNT(*) FROM patients;'}, {'question': 'List all hospitals in Texas sorted by rating descending.', 'gold_sql': "SELECT name, rating FROM hospitals WHERE state = 'TX' ORDER BY rating DESC;"}, {'question': 'What is the average salary of doctors?', 'gold_sql': 'SELECT AVG(salary) FROM doctors;'}, {'question': 'How many doctors specialise in Cardiology?', 'gold_sql': "SELECT COUNT(*) FROM doctors WHERE specialty = 'Cardiology';"}, {'question': 'Which patients have a diagnosis of Diabetes?', 'gold_sql': "SELECT name FROM patients WHERE diagnosis = 'Diabetes';"}, {'question': "List each patient's name and their doctor's name.", 'gold_sql': 'SELECT p.name AS patient, d.name AS doctor FROM patients p JOIN doctors d ON p.doctor_id = d.doctor_id;'}, {'question': 'Which hospital has the most doctors?', 'gold_sql': 'SELECT h.name, COUNT(d.doctor_id) AS num_doctors FROM hospitals h JOIN doctors d ON h.hospital_id = d.hospital_id GROUP BY h.name ORDER BY num_doctors DESC LIMIT 1;'}, {'question': 'List all appointments with patient name and doctor name.', 'gold_sql': 'SELECT p.name AS patient, d.name AS doctor, a.appointment_date FROM appointments a JOIN patients p ON a.patient_id = p.patient_id JOIN doctors d ON a.doctor_id = d.doctor_id;'}, {'question': 'What is the most expensive product?', 'gold_sql': 'SELECT name, price FROM products ORDER BY price DESC LIMIT 1;'}, {'question': "How many orders have status 'Delivered'?", 'gold_sql': "SELECT COUNT(*) FROM orders WHERE status = 'Delivered';"}, {'question': 'List all products in the Electronics category.', 'gold_sql': "SELECT name, price FROM products WHERE category = 'Electronics';"}, {'question': 'What is the total revenue from all orders?', 'gold_sql': 'SELECT SUM(total_amount) FROM orders;'}, {'question': "List each customer's name and the total amount they spent.", 'gold_sql': 'SELECT c.name, SUM(o.total_amount) AS total_spent FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.name ORDER BY total_spent DESC;'}, {'question': 'Which products were ordered more than once?', 'gold_sql': 'SELECT p.name, SUM(oi.quantity) AS total_ordered FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.name HAVING SUM(oi.quantity) > 1;'}, {'question': "List each supplier's name and the number of products they supply.", 'gold_sql': 'SELECT s.name, COUNT(p.product_id) AS num_products FROM suppliers s JOIN products p ON s.supplier_id = p.supplier_id GROUP BY s.name;'}]

def _normalize_sql(sql: str) -> str:
    if not sql:
        return ''
    s = sql.lower().strip()
    s = re.sub('\\s+', ' ', s)
    s = s.rstrip(';').strip()
    return s

def _count_joins(sql: str) -> int:
    return len(re.findall('\\bJOIN\\b', sql, re.IGNORECASE))

def _has_aggregate(sql: str) -> bool:
    return bool(re.search('\\b(AVG|SUM|COUNT|MAX|MIN)\\b', sql, re.IGNORECASE))

def _classify_query(gold_sql: str) -> str:
    join_count = _count_joins(gold_sql)
    if join_count >= 2:
        return 'multi_table_retrieval'
    if join_count == 1:
        return 'join_detection'
    if _has_aggregate(gold_sql):
        return 'column_mapping'
    return 'domain_knowledge'

def _extract_gold_tables(gold_sql: str) -> set[str]:
    pattern = re.compile('(?:FROM|JOIN)\\s+[`\\"\'\\[]?([a-zA-Z_]\\w*)[`\\"\'\\]]?', re.IGNORECASE)
    return {t.lower() for t in pattern.findall(gold_sql)}

def _compare_results(result1: dict, result2: dict) -> bool:
    if result1.get('error') or result2.get('error'):
        return False
    rows1 = result1.get('rows') or []
    rows2 = result2.get('rows') or []
    if len(rows1) != len(rows2):
        return False
    try:
        s1 = sorted([tuple((str(v) for v in r)) for r in rows1])
        s2 = sorted([tuple((str(v) for v in r)) for r in rows2])
        return s1 == s2
    except Exception:
        return False

def _load_benchmark_pairs(n: int=BENCHMARK_SIZE, schema_store: Optional[dict]=None) -> list[dict]:
    pairs = BUILTIN_BENCHMARK_PAIRS[:n]
    logger.info(f'Loaded {len(pairs)} built-in benchmark pairs.')
    return pairs

def run_benchmark(benchmark_data: Optional[list[dict]]=None, schema_store: Optional[dict]=None, faiss_index=None, table_names_ordered: Optional[list[str]]=None, embeddings_matrix=None) -> dict:
    _EMPTY = {'total_queries': 0, 'metrics': {'retrieval_recall_at_5': 0.0, 'retrieval_recall_at_10': 0.0, 'sql_exact_match_accuracy': 0.0, 'sql_execution_match_accuracy': 0.0, 'parsing_success_rate': 0.0, 'average_latency_ms': 0.0}, 'subtask_breakdown': {'multi_table_retrieval': 0.0, 'column_mapping': 0.0, 'join_detection': 0.0, 'domain_knowledge': 0.0}, 'error_analysis': {'retrieval_failures': 0, 'parsing_failures': 0, 'execution_failures': 0, 'logic_errors': 0}}
    if benchmark_data is None:
        benchmark_data = _load_benchmark_pairs(BENCHMARK_SIZE, schema_store)
    if not benchmark_data:
        logger.error('No benchmark data available.')
        return {**_EMPTY, 'error': 'No benchmark data available.'}
    total = len(benchmark_data)
    logger.info(f'Starting benchmark on {total} queries...')
    exact_matches = 0
    execution_matches = 0
    parsing_successes = 0
    retrieval_recall_5_hits = 0
    retrieval_recall_10_hits = 0
    retrieval_failures = 0
    parsing_failures = 0
    execution_failures = 0
    logic_errors = 0
    latencies: list[float] = []
    subtask_totals = {'multi_table_retrieval': 0, 'column_mapping': 0, 'join_detection': 0, 'domain_knowledge': 0}
    subtask_successes = {'multi_table_retrieval': 0, 'column_mapping': 0, 'join_detection': 0, 'domain_knowledge': 0}
    for i, item in enumerate(benchmark_data):
        question = item['question']
        gold_sql = item['gold_sql']
        logger.info(f'\n--- Benchmark {i + 1}/{total} ---')
        logger.info(f'Q: {question[:80]}')
        start = time.time()
        category = _classify_query(gold_sql)
        subtask_totals[category] += 1
        try:
            retrieval_result = retrieve_tables(question, top_k=10, schema_store=schema_store, faiss_index=faiss_index, table_names_ordered=table_names_ordered)
            retrieved_tables = retrieval_result.get('retrieved_tables', [])
        except Exception as e:
            logger.error(f'Retrieval failed: {e}')
            retrieval_failures += 1
            latencies.append((time.time() - start) * 1000)
            continue
        if not retrieved_tables:
            retrieval_failures += 1
            latencies.append((time.time() - start) * 1000)
            continue
        gold_tables = _extract_gold_tables(gold_sql)
        retrieved_set_5 = {t.lower() for t in retrieved_tables[:5]}
        retrieved_set_10 = {t.lower() for t in retrieved_tables[:10]}
        if gold_tables and gold_tables.issubset(retrieved_set_5):
            retrieval_recall_5_hits += 1
        elif not gold_tables:
            retrieval_recall_5_hits += 1
        if gold_tables and gold_tables.issubset(retrieved_set_10):
            retrieval_recall_10_hits += 1
        elif not gold_tables:
            retrieval_recall_10_hits += 1
        try:
            llm_result = generate_sql(question, retrieved_tables[:5], schema_store=schema_store)
        except Exception as e:
            logger.error(f'LLM generation failed: {e}')
            parsing_failures += 1
            latencies.append((time.time() - start) * 1000)
            continue
        generated_sql = llm_result.get('sql') or ''
        if not generated_sql or llm_result.get('error'):
            parsing_failures += 1
            latencies.append((time.time() - start) * 1000)
            continue
        val_result = validate_sql(generated_sql)
        if val_result['is_valid']:
            parsing_successes += 1
            gen_exec = execute_sql(generated_sql)
        else:
            parsing_failures += 1
            gen_exec = {'error': 'invalid sql — skipped execution'}
            latencies.append((time.time() - start) * 1000)
            continue
        gold_exec = execute_sql(gold_sql)
        latency_ms = (time.time() - start) * 1000
        if _normalize_sql(generated_sql) == _normalize_sql(gold_sql):
            exact_matches += 1
        if gen_exec.get('error'):
            execution_failures += 1
        elif gold_exec.get('error'):
            pass
        elif _compare_results(gen_exec, gold_exec):
            execution_matches += 1
            subtask_successes[category] += 1
        else:
            logic_errors += 1
        latencies.append(latency_ms)
        logger.info(f"Done in {latency_ms:.0f}ms | valid={val_result['is_valid']} | exec_match={(_compare_results(gen_exec, gold_exec) if not gen_exec.get('error') and (not gold_exec.get('error')) else False)}")
    avg_latency = float(np.mean(latencies)) if latencies else 0.0
    subtask_breakdown = {cat: round(subtask_successes[cat] / subtask_totals[cat] if subtask_totals[cat] > 0 else 0.0, 4) for cat in subtask_totals}
    result = {'total_queries': total, 'metrics': {'retrieval_recall_at_5': round(retrieval_recall_5_hits / total if total > 0 else 0.0, 4), 'retrieval_recall_at_10': round(retrieval_recall_10_hits / total if total > 0 else 0.0, 4), 'sql_exact_match_accuracy': round(exact_matches / total if total > 0 else 0.0, 4), 'sql_execution_match_accuracy': round(execution_matches / total if total > 0 else 0.0, 4), 'parsing_success_rate': round(parsing_successes / total if total > 0 else 0.0, 4), 'average_latency_ms': round(avg_latency, 2)}, 'subtask_breakdown': subtask_breakdown, 'error_analysis': {'retrieval_failures': retrieval_failures, 'parsing_failures': parsing_failures, 'execution_failures': execution_failures, 'logic_errors': logic_errors}}
    logger.info(f'\nBenchmark complete: {result}')
    return result
if __name__ == '__main__':
    import json
    logging.basicConfig(level=logging.INFO)
    results = run_benchmark()
    print(json.dumps(results, indent=2))