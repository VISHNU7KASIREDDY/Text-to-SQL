# Text-to-SQL Microservice

A production-ready FastAPI microservice that converts natural language questions into executable SQLite queries using semantic table retrieval and an LLM (Meta Llama 4 Maverick via OpenRouter).

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Components](#components)
- [Project Structure](#project-structure)
- [Database Schema](#database-schema)
- [API Endpoints](#api-endpoints)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Benchmark Results](#benchmark-results)
- [Design Decisions](#design-decisions)

---

## Overview

This service accepts a plain-English question (e.g. _"Which instructor teaches Machine Learning?"_) and returns a validated, executed SQL query along with its results. The pipeline uses:

1. **Semantic retrieval** (FAISS + sentence-transformers) to identify relevant tables
2. **LLM-based SQL generation** (Llama 4 Maverick via OpenRouter)
3. **Syntax validation** (sqlglot) to ensure the generated SQL is safe and parseable
4. **Live execution** against a SQLite database

---

## System Architecture

```
User Question (natural language)
          │
          ▼
┌─────────────────────┐
│   FastAPI (main.py) │  ← HTTP entry point, request validation, CORS
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   retrieval.py      │  ← Semantic table retrieval
│                     │
│  SentenceTransformer│  encodes question → 384-dim vector
│  FAISS IndexFlatIP  │  cosine similarity search over table embeddings
│  → top-k tables     │
└────────┬────────────┘
         │  retrieved table names + scores
         ▼
┌─────────────────────┐
│   llm.py            │  ← SQL generation
│                     │
│  OpenRouter API     │  meta-llama/llama-4-maverick
│  Prompt engineering │  schema-grounded, SQLite-strict prompt
│  SQL extraction     │  regex-based extraction from LLM response
└────────┬────────────┘
         │  raw SQL string
         ▼
┌─────────────────────┐
│   validation.py     │  ← Safety & syntax check
│                     │
│  sqlglot (SQLite)   │  parse-tree validation
│  keyword blocklist  │  blocks DROP/DELETE/INSERT/UPDATE/ALTER
└────────┬────────────┘
         │  validated SQL
         ▼
┌─────────────────────┐
│   execution.py      │  ← Live query execution
│                     │
│  sqlite3            │  connects to database.db
│  fetchmany(100)     │  safe row limit
└────────┬────────────┘
         │
         ▼
     JSON Response
  (sql, rows, columns,
   model_used, confidence)
```

---

## Components

### `main.py` — FastAPI Application
- Defines all HTTP routes and Pydantic request/response models
- Loads the schema store and FAISS index at startup via the `lifespan` context manager
- Stores shared state (`schema_store`, `faiss_index`, `table_names_ordered`) in `app_state`
- Adds CORS middleware and HTTP request logging middleware

### `schema_store.py` — Schema Indexing
- Reads `schema_cache.json` which contains table definitions (columns, types, CREATE statements)
- Uses `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dimensions) to embed each table's description
- Builds a `faiss.IndexFlatIP` (inner product / cosine similarity after L2 normalisation) over all table embeddings
- Exposes `get_schema_store()` which returns the `(tables, faiss_index, table_names)` triple

### `retrieval.py` — Semantic Table Retrieval
- Encodes the user's question using the same embedding model
- Performs L2-normalised FAISS search to find the top-k most similar tables
- Returns table names, per-table relevance scores (0–1), overall confidence, and column details
- Gracefully handles edge cases (empty questions, index size limits)

### `llm.py` — SQL Generation
- Builds a structured prompt including the relevant table schemas, strict SQLite rules, and few-shot examples
- Calls the **OpenRouter API** (`meta-llama/llama-4-maverick`) using the OpenAI-compatible SDK
- Extracts the SQL from the LLM response using regex (markdown code blocks → `SQL:` markers → raw SELECT)
- Implements 2-attempt retry with 2-second backoff on API failure
- Falls back to a built-in mock response dictionary if the API key is missing or invalid
- Logs every LLM interaction (question, prompt, response, extracted SQL) to `llm_logs.txt`

### `validation.py` — SQL Safety & Syntax Validation
- Rejects any query that doesn't start with `SELECT`
- Blocks dangerous mutation keywords (`DROP`, `DELETE`, `INSERT`, `UPDATE`, `ALTER`, `TRUNCATE`, `CREATE`) via word-boundary regex
- Uses `sqlglot` to parse the SQL with SQLite dialect, catching any syntax errors

### `execution.py` — SQL Execution
- Connects to `database.db` (SQLite) and executes the validated SQL
- Returns up to 100 rows, column names, row count, and any execution error
- Fully exception-safe — all errors are returned as structured JSON, never as unhandled exceptions

### `metrics.py` — Benchmarking
- Contains 25 hand-crafted question/gold-SQL pairs covering the university, hospital, and e-commerce domains
- Classifies each query into a subtask category: `multi_table_retrieval`, `join_detection`, `column_mapping`, `domain_knowledge`
- Measures: retrieval recall @5 / @10, SQL exact match, execution match, parsing success rate, average latency
- Compares execution results by sorting rows and converting values to strings (order-insensitive comparison)

### `setup_db.py` — Database Setup
- Creates and populates the SQLite database with 3 domain datasets: university, hospital, e-commerce
- Generates `schema_cache.json` used by the schema store at runtime

---

## Project Structure

```
Text-to-SQL/
├── main.py            # FastAPI app, routes, request/response models
├── llm.py             # LLM SQL generation via OpenRouter
├── retrieval.py       # FAISS-based semantic table retrieval
├── schema_store.py    # Embedding model, FAISS index, schema cache loader
├── validation.py      # SQL safety and syntax validation
├── execution.py       # SQLite query execution
├── metrics.py         # Benchmark runner and evaluation metrics
├── setup_db.py        # Database and schema cache initialisation
├── schema_cache.json  # Pre-built table schema definitions
├── database.db        # SQLite database (university + hospital + e-commerce)
├── requirements.txt   # Python dependencies
├── .env               # API keys (not committed)
├── .env.example       # Template for required environment variables
├── .gitignore
└── README.md
```

---

## Database Schema

The SQLite database (`database.db`) contains 3 domain datasets with 6 active tables in the university domain:

| Table | Key Columns |
|-------|-------------|
| `students` | student_id, first_name, last_name, age, gpa, dept_id, email, major, year |
| `departments` | dept_id, dept_name, building, budget |
| `courses` | course_id, course_name, dept_id, credits, description |
| `instructors` | instructor_id, name, dept_id, salary, title |
| `enrollments` | enrollment_id, student_id, course_id, grade, semester |
| `teaches` | teaches_id, instructor_id, course_id, semester, year |

---

## API Endpoints

Base URL: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`

---

### `GET /`
Returns service status and metadata.

**Response**
```json
{
  "service": "Text-to-SQL Microservice",
  "version": "1.0.0",
  "status": "ready",
  "tables_loaded": 6,
  "docs": "/docs"
}
```

---

### `GET /health`
Health check endpoint.

**Response**
```json
{
  "status": "ok",
  "tables_loaded": 6
}
```

---

### `POST /retrieve`
Retrieves the most semantically relevant database tables for a given question using FAISS cosine similarity search.

**Request**
```json
{
  "question": "How many students are in each department?"
}
```

**Response**
```json
{
  "retrieved_tables": ["students", "departments", "enrollments", "courses", "teaches"],
  "scores": [0.5143, 0.4987, 0.4778, 0.4658, 0.4336],
  "confidence": 0.478,
  "details": {
    "students": {
      "relevance_score": 0.5143,
      "reason": "Table students matched with score 0.51",
      "columns": ["student_id", "first_name", "last_name", "age", "gpa", "dept_id", "email", "major", "year"]
    }
  }
}
```

---

### `POST /generate-sql`
Full pipeline: retrieve → generate → validate → execute.

**Request**
```json
{
  "question": "Which instructor teaches Machine Learning?",
  "use_retrieved_context": true
}
```

**Response**
```json
{
  "sql": "SELECT i.name FROM instructors i JOIN teaches t ON i.instructor_id = t.instructor_id JOIN courses c ON t.course_id = c.course_id WHERE c.course_name = 'Machine Learning';",
  "retrieved_tables": ["teaches", "instructors", "courses", "students", "enrollments"],
  "is_valid_syntax": true,
  "parsing_errors": null,
  "confidence": 0.2328,
  "execution_result": {
    "columns": ["name"],
    "rows": [["Dr. Smith"]],
    "row_count": 1,
    "error": null
  },
  "prompt_used": "...",
  "model_used": "meta-llama/llama-4-maverick"
}
```

**Fields**

| Field | Description |
|-------|-------------|
| `sql` | Generated SQL query |
| `retrieved_tables` | Tables selected by FAISS retrieval |
| `is_valid_syntax` | Whether sqlglot parsed the SQL successfully |
| `parsing_errors` | List of syntax errors if invalid |
| `confidence` | Mean cosine similarity score of retrieved tables |
| `execution_result` | Columns, rows (up to 100), row count, or error |
| `model_used` | LLM model identifier |

---

### `POST /benchmark`
Runs an automated benchmark over 25 question/gold-SQL pairs. Takes ~60–90 seconds (makes 25 real LLM calls).

**Response**
```json
{
  "total_queries": 25,
  "metrics": {
    "retrieval_recall_at_5": 0.36,
    "retrieval_recall_at_10": 0.40,
    "sql_exact_match_accuracy": 0.12,
    "sql_execution_match_accuracy": 0.28,
    "parsing_success_rate": 0.88,
    "average_latency_ms": 4582.28
  },
  "subtask_breakdown": {
    "multi_table_retrieval": 0.6667,
    "column_mapping": 0.125,
    "join_detection": 0.25,
    "domain_knowledge": 0.3333
  },
  "error_analysis": {
    "retrieval_failures": 0,
    "parsing_failures": 3,
    "execution_failures": 1,
    "logic_errors": 2
  }
}
```

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- An [OpenRouter](https://openrouter.ai) API key

### Steps

```bash
# 1. Clone the repository
git clone <repo-url>
cd Text-to-SQL

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate       # macOS / Linux
venv\Scripts\activate          # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and add your OpenRouter API key

# 5. Set up the database and schema cache
python setup_db.py

# 6. Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000/docs` for the interactive Swagger UI.

---

## Configuration

Copy `.env.example` to `.env` and set the following:

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | Your OpenRouter API key (`sk-or-v1-...`) |

The service uses `meta-llama/llama-4-maverick` by default. To switch models, update the `model` parameter in `llm.py`.

---

## Benchmark Results

Evaluated on 25 queries across university, hospital, and e-commerce domains using `meta-llama/llama-4-maverick` via OpenRouter.

| Metric | Score |
|--------|-------|
| Parsing Success Rate | **88%** |
| Execution Match Accuracy | **28%** |
| SQL Exact Match Accuracy | **12%** |
| Retrieval Recall @5 | **36%** |
| Retrieval Recall @10 | **40%** |
| Average Latency | **~4.6 s** |

**Subtask Breakdown**

| Subtask | Accuracy |
|---------|----------|
| Multi-table retrieval | 66.7% |
| Domain knowledge | 33.3% |
| Join detection | 25.0% |
| Column mapping | 12.5% |

**Key observations:**
- The pipeline never crashes (0 retrieval failures), showing strong robustness
- Multi-table queries perform best (66.7%) — the FAISS retriever handles broad context well
- Column mapping is the weakest area (12.5%) — the LLM sometimes selects incorrect columns when schema names are ambiguous
- Retrieval recall @5 (36%) is the main bottleneck — improving it would directly raise execution accuracy

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **FAISS IndexFlatIP** with L2 normalisation | Cosine similarity is ideal for semantic matching; exact search is fast enough for a small number of tables (≤100) |
| **all-MiniLM-L6-v2** embeddings | Lightweight (384-dim), fast, good quality for short text like table/column descriptions |
| **OpenRouter + Llama 4 Maverick** | OpenAI-compatible API, supports a wide range of models, generous free tier; Llama 4 Maverick is fast and capable at structured output |
| **sqlglot validation** | Dialect-aware parsing catches SQLite-incompatible syntax before hitting the database |
| **Fallback mock mode** | If no valid API key is present, the service still works via a built-in response dictionary — useful for local development |
| **fetchmany(100)** cap | Prevents large result sets from overwhelming the API response |
| **Prompt few-shot examples** | Three concrete examples in the prompt consistently improve SQLite syntax compliance and alias usage |