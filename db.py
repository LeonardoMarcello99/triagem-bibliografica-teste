import sqlite3
from config import DB_PATH


def _session_db_path():
    """Retorna banco exclusivo da sessão Streamlit, sem dados compartilhados."""
    import streamlit as st
    try:
        path = st.session_state.get('_litscope_session_db')
    except Exception:
        path = None
    if not path:
        raise RuntimeError('Sessão web não inicializada; recarregue a página.')
    return path


def connect():
    con = sqlite3.connect(_session_db_path(), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=30000')
    con.execute('''CREATE TABLE IF NOT EXISTS articles (
        pmid TEXT PRIMARY KEY, title TEXT NOT NULL, abstract TEXT,
        year TEXT, journal TEXT, doi TEXT, url TEXT,
        ai_label TEXT, ai_reason TEXT, ai_criteria TEXT,
        human_label TEXT, human_note TEXT, reviewed_at TEXT,
        model TEXT, criteria_hash TEXT, analyzed_at TEXT)''')
    con.execute('''CREATE TABLE IF NOT EXISTS datasets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        query TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    dataset_columns={r[1] for r in con.execute('PRAGMA table_info(datasets)')}
    if 'inclusion_criteria' not in dataset_columns:
        con.execute('ALTER TABLE datasets ADD COLUMN inclusion_criteria TEXT')
    if 'exclusion_criteria' not in dataset_columns:
        con.execute('ALTER TABLE datasets ADD COLUMN exclusion_criteria TEXT')
    for column, sqltype in [('identified_total','INTEGER'),('prisma_screen_excluded','INTEGER'),('prisma_not_retrieved','INTEGER'),('prisma_fulltext_excluded','INTEGER'),('prisma_included','INTEGER')]:
        if column not in dataset_columns:
            con.execute(f'ALTER TABLE datasets ADD COLUMN {column} {sqltype}')
    con.execute('''CREATE TABLE IF NOT EXISTS dataset_articles (
        dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
        pmid TEXT NOT NULL REFERENCES articles(pmid),
        ai_label TEXT, ai_reason TEXT, ai_criteria TEXT,
        human_label TEXT, human_note TEXT, reviewed_at TEXT,
        model TEXT, criteria_hash TEXT, analyzed_at TEXT,
        PRIMARY KEY(dataset_id,pmid))''')
    da_columns={r[1] for r in con.execute('PRAGMA table_info(dataset_articles)')}
    if 'duplicate_removed' not in da_columns:
        con.execute('ALTER TABLE dataset_articles ADD COLUMN duplicate_removed INTEGER NOT NULL DEFAULT 0')
    # Migração incremental: as coleções e avaliações existentes permanecem intactas.
    columns={r[1] for r in con.execute('PRAGMA table_info(articles)')}
    if 'source' not in columns:
        con.execute("ALTER TABLE articles ADD COLUMN source TEXT DEFAULT 'PubMed'")
    if 'source_id' not in columns:
        con.execute('ALTER TABLE articles ADD COLUMN source_id TEXT')
    if 'authors' not in columns:
        con.execute('ALTER TABLE articles ADD COLUMN authors TEXT')
    con.execute("""CREATE TABLE IF NOT EXISTS article_extractions (
        dataset_id INTEGER NOT NULL, pmid TEXT NOT NULL,
        pdf_name TEXT, model TEXT, extracted_json TEXT,
        verified INTEGER NOT NULL DEFAULT 0,
        extracted_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(dataset_id,pmid))""")
    con.execute('PRAGMA foreign_keys=ON')
    # Migração não destrutiva: a base antiga é preservada e recebe uma coleção própria.
    if not con.execute('SELECT 1 FROM datasets LIMIT 1').fetchone():
        legacy = con.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
        if legacy:
            cur = con.execute("INSERT INTO datasets(name,query) VALUES ('Base original (migração v2)', 'Importação da versão anterior')")
            con.execute('''INSERT INTO dataset_articles
                (dataset_id,pmid,ai_label,ai_reason,ai_criteria,human_label,human_note,reviewed_at,model,criteria_hash,analyzed_at)
                SELECT ?,pmid,ai_label,ai_reason,ai_criteria,human_label,human_note,reviewed_at,model,criteria_hash,analyzed_at FROM articles''', (cur.lastrowid,))
    con.commit()
    return con


def datasets():
    with connect() as con:
        return [dict(x) for x in con.execute('''SELECT d.*, COUNT(da.pmid) total,
            SUM(CASE WHEN da.ai_label IS NOT NULL THEN 1 ELSE 0 END) processed
            FROM datasets d LEFT JOIN dataset_articles da ON da.dataset_id=d.id
            GROUP BY d.id ORDER BY d.id DESC''')]


def save_screening_criteria(did, inclusion, exclusion):
    """Persiste os critérios usados para iniciar a triagem nesta coleção."""
    with connect() as con:
        con.execute('''UPDATE datasets
            SET inclusion_criteria=?, exclusion_criteria=?
            WHERE id=?''', (inclusion, exclusion, did))


def create_dataset(name, query, rows, identified_total=None):
    with connect() as con:
        cur = con.execute('INSERT INTO datasets(name,query) VALUES (?,?)', (name,query))
        did = cur.lastrowid
        con.execute('UPDATE datasets SET identified_total=? WHERE id=?', (identified_total if identified_total is not None else len(rows), did))
        rows=[{**row, 'authors':row.get('authors') or ''} for row in rows]
        con.executemany('''INSERT INTO articles (pmid,title,abstract,year,journal,doi,url,source,source_id,authors)
            VALUES (:pmid,:title,:abstract,:year,:journal,:doi,:url,:source,:source_id,:authors)
            ON CONFLICT(pmid) DO UPDATE SET title=excluded.title,
            abstract=excluded.abstract, year=excluded.year, journal=excluded.journal,
            doi=excluded.doi,url=excluded.url,source=excluded.source,source_id=excluded.source_id,
            authors=CASE WHEN excluded.authors IS NOT NULL AND excluded.authors!='' THEN excluded.authors ELSE articles.authors END''', rows)
        con.executemany('INSERT OR IGNORE INTO dataset_articles(dataset_id,pmid) VALUES (?,?)',
                        [(did,r['pmid']) for r in rows])
        return did


def delete_dataset(did):
    with connect() as con:
        con.execute('DELETE FROM article_extractions WHERE dataset_id=?', (did,))
        con.execute('DELETE FROM dataset_articles WHERE dataset_id=?', (did,))
        con.execute('DELETE FROM datasets WHERE id=?', (did,))
        # Artigos compartilhados por outras coleções nunca são apagados.
        con.execute('DELETE FROM articles WHERE pmid NOT IN (SELECT pmid FROM dataset_articles)')


def all_articles(did):
    with connect() as con:
        return [dict(x) for x in con.execute('''SELECT a.pmid,a.title,a.abstract,a.year,a.journal,a.doi,a.url,a.source,a.source_id,a.authors,
            da.ai_label,da.ai_reason,da.ai_criteria,da.human_label,da.human_note,
            da.reviewed_at,da.model,da.criteria_hash,da.analyzed_at,da.duplicate_removed
            FROM dataset_articles da JOIN articles a ON a.pmid=da.pmid
            WHERE da.dataset_id=? ORDER BY a.pmid DESC''', (did,))]


def save_ai(did, pmid, label, reason, criteria, model, key):
    with connect() as con:
        con.execute('''UPDATE dataset_articles SET ai_label=?,ai_reason=?,ai_criteria=?,
            model=?,criteria_hash=?,analyzed_at=CURRENT_TIMESTAMP
            WHERE dataset_id=? AND pmid=?''', (label,reason,criteria,model,key,did,pmid))


def save_review(did, pmid, label, note):
    with connect() as con:
        con.execute('''UPDATE dataset_articles SET human_label=?,human_note=?,reviewed_at=CURRENT_TIMESTAMP
            WHERE dataset_id=? AND pmid=?''', (label,note,did,pmid))


def save_extraction(did,pmid,pdf_name,model,data):
    import json
    with connect() as con:
        con.execute("""INSERT INTO article_extractions
            (dataset_id,pmid,pdf_name,model,extracted_json,verified,extracted_at)
            VALUES (?,?,?,?,?,0,CURRENT_TIMESTAMP)
            ON CONFLICT(dataset_id,pmid) DO UPDATE SET
            pdf_name=excluded.pdf_name,model=excluded.model,
            extracted_json=excluded.extracted_json,verified=0,
            extracted_at=CURRENT_TIMESTAMP""",
            (did,pmid,pdf_name,model,json.dumps(data,ensure_ascii=False)))


def get_extractions(did):
    import json
    with connect() as con:
        rows=[dict(r) for r in con.execute("""SELECT * FROM article_extractions
            WHERE dataset_id=? ORDER BY extracted_at DESC""",(did,))]
    for r in rows:
        r['data']=json.loads(r.pop('extracted_json'))
    return rows


def verify_extraction(did,pmid,verified):
    with connect() as con:
        con.execute('UPDATE article_extractions SET verified=? WHERE dataset_id=? AND pmid=?',
                    (int(verified),did,pmid))


def delete_review(did, pmid):
    """Remove apenas a decisão humana de uma coleção, mantendo artigo e IA."""
    with connect() as con:
        con.execute("UPDATE dataset_articles SET human_label=NULL,human_note=NULL,reviewed_at=NULL WHERE dataset_id=? AND pmid=?",(did,pmid))


def delete_extraction(did, pmid):
    """Remove somente a extração selecionada da coleção."""
    with connect() as con:
        con.execute('DELETE FROM article_extractions WHERE dataset_id=? AND pmid=?',(did,pmid))


def set_duplicate_removed(did, pmid, removed):
    """Marca duplicata sem excluir artigo, revisão ou extração."""
    with connect() as con:
        con.execute('UPDATE dataset_articles SET duplicate_removed=? WHERE dataset_id=? AND pmid=?',
                    (int(bool(removed)),did,pmid))


def set_prisma_manual(did, screened_excluded, not_retrieved, fulltext_excluded, included):
    with connect() as con:
        con.execute("""UPDATE datasets SET prisma_screen_excluded=?,prisma_not_retrieved=?,
            prisma_fulltext_excluded=?,prisma_included=? WHERE id=?""",
            (screened_excluded,not_retrieved,fulltext_excluded,included,did))


def restore_collection(dataset, articles, extractions):
    """Restaura em NOVA coleção, com transação única e sem sobrescrever revisões existentes."""
    import json
    from collection_tools import read_backup, BACKUP_FORMAT
    # Valida novamente mesmo se chamada fora da interface.
    meta, rows, ext = read_backup(json.dumps({'format':BACKUP_FORMAT,'dataset':dataset,
                                                'articles':articles,'extractions':extractions},ensure_ascii=False).encode())
    with connect() as con:
        name=str(meta.get('name') or 'Coleção restaurada')[:200]+' (restaurada)'
        cur=con.execute('INSERT INTO datasets(name,query) VALUES (?,?)',(name,str(meta.get('query') or '')))
        did=cur.lastrowid
        for key in ('inclusion_criteria','exclusion_criteria','identified_total',
                    'prisma_screen_excluded','prisma_not_retrieved','prisma_fulltext_excluded','prisma_included'):
            value=meta.get(key)
            if key.startswith('prisma_') or key=='identified_total':
                value=int(value) if isinstance(value,int) and value>=0 else None
            con.execute(f'UPDATE datasets SET {key}=? WHERE id=?',(value,did))
        for row in rows:
            # Não sobrescreve metadados de artigos compartilhados com outras coleções.
            con.execute('''INSERT OR IGNORE INTO articles(pmid,title,abstract,year,journal,doi,url,source,source_id,authors)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',tuple(row.get(k) for k in ('pmid','title','abstract','year','journal','doi','url','source','source_id','authors')))
            con.execute('''INSERT INTO dataset_articles
                (dataset_id,pmid,ai_label,ai_reason,ai_criteria,human_label,human_note,
                 reviewed_at,model,criteria_hash,analyzed_at,duplicate_removed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (did,row['pmid'],*[row.get(k) for k in ('ai_label','ai_reason','ai_criteria',
                    'human_label','human_note','reviewed_at','model','criteria_hash','analyzed_at')],
                    int(bool(row.get('duplicate_removed')))))
        for item in ext:
            con.execute('''INSERT INTO article_extractions(dataset_id,pmid,pdf_name,model,extracted_json,verified)
                VALUES (?,?,?,?,?,?)''',(did,item['pmid'],str(item.get('pdf_name') or ''),
                str(item.get('model') or ''),json.dumps(item['data'],ensure_ascii=False),int(bool(item.get('verified')))))
    return did


def update_extraction_field(did, pmid, field, value, page, evidence):
    """Correção humana de um campo: mantém registro de que houve edição e desmarca verificação global."""
    import json
    with connect() as con:
        row=con.execute('SELECT extracted_json FROM article_extractions WHERE dataset_id=? AND pmid=?',
                        (did,pmid)).fetchone()
        if row is None:
            raise ValueError('Extração não encontrada.')
        data=json.loads(row['extracted_json'])
        if field not in data:
            raise ValueError('Campo não encontrado.')
        data[field]={'value':value.strip() or None,'page':page,'evidence':evidence.strip(),
                     'evidence_status':'editado_manualmente'}
        con.execute('UPDATE article_extractions SET extracted_json=?,verified=0 WHERE dataset_id=? AND pmid=?',
                    (json.dumps(data,ensure_ascii=False),did,pmid))
