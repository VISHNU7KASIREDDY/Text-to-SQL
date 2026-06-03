import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from execution import execute_sql
from llm import generate_sql
from metrics import run_benchmark
from retrieval import retrieve_tables
from schema_store import get_schema_store
from validation import validate_sql
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(), logging.FileHandler('app.log')])
logger = logging.getLogger(__name__)
app_state: dict[str, Any] = {'schema_store': None, 'faiss_index': None, 'table_names_ordered': None, 'ready': False}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Startup: loading schema store and FAISS index...')
    try:
        store, faiss_index, table_names = get_schema_store()
        app_state['schema_store'] = store
        app_state['faiss_index'] = faiss_index
        app_state['table_names_ordered'] = table_names
        app_state['ready'] = True
        logger.info(f'Ready. FAISS index built with {faiss_index.ntotal} table vectors. Tables loaded: {len(store)}')
    except Exception as e:
        logger.error(f'Failed to load schema store at startup: {e}', exc_info=True)
        raise RuntimeError(f'Could not initialise schema store: {e}. Make sure you have run setup_db.py first.')
    yield
    logger.info('Shutdown.')
app = FastAPI(title='Text-to-SQL Microservice', description='Convert natural language questions into executable SQL queries using semantic table retrieval (FAISS + sentence-transformers) and LLM-based SQL generation (Claude). Built on the AppliedResearch/BEAVER dataset.', version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

@app.middleware('http')
async def log_requests(request: Request, call_next):
    start = time.time()
    logger.info(f'-> {request.method} {request.url.path}')
    response = await call_next(request)
    elapsed = (time.time() - start) * 1000
    logger.info(f'<- {request.method} {request.url.path} status={response.status_code} {elapsed:.0f}ms')
    return response

class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description='Natural language question (1–500 characters).', examples=['How many students are in each department?'])

    @field_validator('question')
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('question must not be blank or whitespace-only.')
        return v.strip()

class TableDetail(BaseModel):
    relevance_score: float
    reason: str
    columns: list[str]

class RetrieveResponse(BaseModel):
    retrieved_tables: list[str]
    scores: list[float]
    confidence: float
    details: dict[str, TableDetail]

class GenerateSQLRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description='Natural language question (1–500 characters).', examples=['How many students are enrolled in Computer Science?'])
    use_retrieved_context: bool = Field(default=True, description='If True, uses semantic retrieval to select relevant tables.')

    @field_validator('question')
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('question must not be blank or whitespace-only.')
        return v.strip()

class ExecutionResult(BaseModel):
    columns: Optional[list[str]] = None
    rows: Optional[list[list]] = None
    row_count: Optional[int] = None
    error: Optional[str] = None

class GenerateSQLResponse(BaseModel):
    sql: Optional[str]
    retrieved_tables: list[str]
    is_valid_syntax: bool
    parsing_errors: Optional[list[str]] = None
    confidence: float
    execution_result: Optional[ExecutionResult] = None
    prompt_used: str
    model_used: Optional[str] = None

class BenchmarkMetrics(BaseModel):
    retrieval_recall_at_5: float
    retrieval_recall_at_10: float
    sql_exact_match_accuracy: float
    sql_execution_match_accuracy: float
    parsing_success_rate: float
    average_latency_ms: float

class SubtaskBreakdown(BaseModel):
    multi_table_retrieval: float
    column_mapping: float
    join_detection: float
    domain_knowledge: float

class ErrorAnalysis(BaseModel):
    retrieval_failures: int
    parsing_failures: int
    execution_failures: int
    logic_errors: int

class BenchmarkResponse(BaseModel):
    total_queries: int
    metrics: BenchmarkMetrics
    subtask_breakdown: SubtaskBreakdown
    error_analysis: ErrorAnalysis

def _assert_ready() -> None:
    if not app_state['ready']:
        raise HTTPException(status_code=503, detail='Service not ready — schema store is still loading.')

@app.get('/health', tags=['Health'])
async def health():
    tables_loaded = len(app_state['schema_store']) if app_state['schema_store'] else 0
    return {'status': 'ok', 'tables_loaded': tables_loaded}

@app.get('/', tags=['Health'])
async def root():
    tables_loaded = len(app_state['schema_store']) if app_state['schema_store'] else 0
    return {'service': 'Text-to-SQL Microservice', 'version': '1.0.0', 'status': 'ready' if app_state['ready'] else 'initialising', 'tables_loaded': tables_loaded, 'docs': '/docs'}

@app.post('/retrieve', response_model=RetrieveResponse, tags=['Retrieval'], summary='Retrieve relevant database tables for a natural language question')
async def retrieve_endpoint(request: RetrieveRequest):
    _assert_ready()
    logger.info(f"POST /retrieve | question='{request.question[:60]}'")
    try:
        result = retrieve_tables(question=request.question, top_k=5, schema_store=app_state['schema_store'], faiss_index=app_state['faiss_index'], table_names_ordered=app_state['table_names_ordered'])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f'/retrieve error: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    if result.get('error'):
        raise HTTPException(status_code=500, detail=result['error'])
    return RetrieveResponse(**result)

@app.post('/generate-sql', response_model=GenerateSQLResponse, tags=['SQL Generation'], summary='Full pipeline: retrieve -> generate -> validate -> execute')
async def generate_sql_endpoint(request: GenerateSQLRequest):
    _assert_ready()
    logger.info(f"POST /generate-sql | question='{request.question[:60]}'")
    t_start = time.time()
    retrieved_tables: list[str] = []
    confidence: float = 0.0
    if request.use_retrieved_context:
        try:
            ret = retrieve_tables(question=request.question, top_k=5, schema_store=app_state['schema_store'], faiss_index=app_state['faiss_index'], table_names_ordered=app_state['table_names_ordered'])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Retrieval error: {e}')
        retrieved_tables = ret.get('retrieved_tables', [])
        confidence = ret.get('confidence', 0.0)
        if not retrieved_tables:
            raise HTTPException(status_code=400, detail='No relevant tables found for the question.')
    else:
        retrieved_tables = list(app_state['schema_store'].keys())[:10]
        confidence = 1.0
    gen_result = generate_sql(question=request.question, retrieved_tables=retrieved_tables, schema_store=app_state['schema_store'])
    if gen_result.get('error'):
        raise HTTPException(status_code=500, detail=f"SQL generation failed: {gen_result['error']}")
    generated_sql: str = gen_result.get('sql') or ''
    prompt_used: str = gen_result.get('prompt_used', '')
    model_used: str = gen_result.get('model_used', '')
    val_result = validate_sql(generated_sql)
    is_valid: bool = val_result['is_valid']
    parsing_errors: Optional[list[str]] = val_result['errors']
    execution_result: Optional[ExecutionResult] = None
    if is_valid:
        exec_res = execute_sql(generated_sql)
        if exec_res.get('error'):
            execution_result = ExecutionResult(columns=None, rows=None, row_count=0, error=exec_res['error'])
        else:
            execution_result = ExecutionResult(columns=exec_res['columns'], rows=exec_res['rows'], row_count=exec_res['row_count'])
    elapsed = (time.time() - t_start) * 1000
    logger.info(f'POST /generate-sql complete in {elapsed:.0f}ms | valid={is_valid} | tables={retrieved_tables}')
    return GenerateSQLResponse(sql=generated_sql, retrieved_tables=retrieved_tables, is_valid_syntax=is_valid, parsing_errors=parsing_errors, confidence=confidence, execution_result=execution_result, prompt_used=prompt_used, model_used=model_used)

@app.post('/benchmark', response_model=BenchmarkResponse, tags=['Benchmark'], summary='Run automated benchmark on 25 Beaver dataset question+gold_sql pairs')
async def benchmark_endpoint():
    _assert_ready()
    logger.info('POST /benchmark | Starting benchmark run...')
    try:
        results = run_benchmark(schema_store=app_state['schema_store'], faiss_index=app_state['faiss_index'], table_names_ordered=app_state['table_names_ordered'])
    except Exception as e:
        logger.error(f'/benchmark error: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    if results.get('total_queries', 0) == 0 and results.get('error'):
        raise HTTPException(status_code=500, detail=f"Benchmark failed: {results['error']}")
    return BenchmarkResponse(total_queries=results['total_queries'], metrics=BenchmarkMetrics(**results['metrics']), subtask_breakdown=SubtaskBreakdown(**results['subtask_breakdown']), error_analysis=ErrorAnalysis(**results['error_analysis']))