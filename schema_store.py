import json
import logging
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from pathlib import Path
logger = logging.getLogger(__name__)
SCHEMA_CACHE_PATH = Path('schema_cache.json')
with open(SCHEMA_CACHE_PATH, 'r', encoding='utf-8') as f:
    schema_data = json.load(f)
db_id = schema_data['db_id']
tables = schema_data['tables']
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
descriptions = []
table_names = []
table_schemas = {}
table_columns = {}
for t_name, info in tables.items():
    col_str_list = [f"{col['name']} {col['type']}" for col in info['columns']]
    desc = f"{t_name}: {', '.join(col_str_list)}"
    descriptions.append(desc)
    table_names.append(t_name)
    table_schemas[t_name] = info['create_statement']
    table_columns[t_name] = [col['name'] for col in info['columns']]
embeddings = embedding_model.encode(descriptions, convert_to_numpy=True)
embeddings = embeddings.astype('float32')
faiss.normalize_L2(embeddings)
dimension = embeddings.shape[1]
faiss_index = faiss.IndexFlatIP(dimension)
faiss_index.add(embeddings)
print(f'Schema store ready: {len(table_names)} tables indexed in FAISS')
print(f'Embedding dimension: {dimension}')

def get_schema_store():
    return (tables, faiss_index, table_names)