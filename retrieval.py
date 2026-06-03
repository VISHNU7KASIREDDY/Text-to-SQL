import numpy as np
import faiss
import schema_store as schema_store_module

def retrieve_tables(question: str, top_k: int=5, schema_store: dict=None, faiss_index=None, table_names_ordered: list[str]=None) -> dict:
    if not question or not question.strip():
        raise ValueError('Question cannot be empty')
    question = question.strip()
    if faiss_index is None:
        faiss_index = schema_store_module.faiss_index
    if table_names_ordered is None:
        table_names_ordered = schema_store_module.table_names
    q_vec = schema_store_module.embedding_model.encode([question])
    q_vec = q_vec.astype('float32')
    faiss.normalize_L2(q_vec)
    effective_k = min(top_k, faiss_index.ntotal)
    scores, indices = faiss_index.search(q_vec, effective_k)
    raw_scores = scores[0].tolist()
    raw_indices = indices[0].tolist()
    retrieved_tables = []
    mapped_scores = []
    details = {}

    def get_columns(t_name):
        if schema_store is not None and t_name in schema_store:
            cols = schema_store[t_name].get('columns', [])
            if cols and isinstance(cols[0], dict):
                return [c['name'] for c in cols]
            return cols
        return schema_store_module.table_columns.get(t_name, [])
    for idx, score in zip(raw_indices, raw_scores):
        if idx < 0 or idx >= len(table_names_ordered):
            continue
        t_name = table_names_ordered[idx]
        retrieved_tables.append(t_name)
        score_val = max(0.0, min(1.0, float(score)))
        score_val = round(score_val, 4)
        mapped_scores.append(score_val)
        details[t_name] = {'relevance_score': score_val, 'reason': f'Table {t_name} matched with score {score_val:.2f}', 'columns': get_columns(t_name)}
    confidence = round(float(np.mean(mapped_scores)), 4) if mapped_scores else 0.0
    return {'retrieved_tables': retrieved_tables, 'scores': mapped_scores, 'confidence': confidence, 'details': details}