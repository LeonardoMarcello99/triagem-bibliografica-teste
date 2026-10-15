"""Conectores de fontes; nunca usa endpoints não documentados da Cochrane."""
import csv
import io
import re
import requests

FIELDS = {
    'PubMed': {'Todos os campos': '[All Fields]', 'Título': '[Title]', 'Título/Resumo': '[Title/Abstract]', 'Resumo': '[Abstract]', 'MeSH Terms': '[MeSH Terms]', 'Autor': '[Author]', 'Periódico': '[Journal]'},
    'Embase': {'Todos os campos': '', 'Título': ':ti', 'Título/Resumo': ':ti,ab', 'Resumo': ':ab', 'Emtree (descritor)': '/exp', 'Autor': ':au'},
    'Cochrane': {'Todos os campos': '', 'Título': ':ti', 'Título/Resumo': ':ti,ab', 'Resumo': ':ab', 'Palavras-chave': ':kw'},
}


def term_for_source(source, term, field):
    term = term.strip()
    if not term:
        raise ValueError('Informe um termo de pesquisa.')
    suffix = FIELDS[source][field]
    if source == 'PubMed':
        return f'({term}{suffix})'
    if source == 'Embase' and field == 'Emtree (descritor)':
        return f"'{term.strip(chr(34)).strip(chr(39))}'/exp"
    if suffix:
        return f'({term}{suffix})'
    return f'({term})'


def add_term(query, term, field, operator, source):
    fragment = term_for_source(source, term, field)
    return (query.strip() + ' ' + operator + ' ' + fragment) if query.strip() else fragment


def _text(value):
    if isinstance(value, dict):
        return str(value.get('$') or value.get('#text') or '')
    if isinstance(value, list):
        return ' '.join(_text(x) for x in value)
    return str(value or '')


def _normalize(record, source, number):
    title = str(record.get('title') or '').strip()
    if not title:
        return None
    doi = str(record.get('doi') or '').strip().removeprefix('https://doi.org/')
    pmid = str(record.get('pubmed_id') or '').strip()
    external = str(record.get('external_id') or '').strip()
    # Prefere IDs da base; evita colisões entre registros de bases diferentes.
    if source == 'PubMed' and pmid:
        uid = pmid
    elif external:
        uid = f'{source.upper()}:{external}'
    elif doi:
        uid = f'{source.upper()}:DOI:{doi.lower()}'
    else:
        import hashlib
        uid = f'{source.upper()}:HASH:{hashlib.sha256((title.lower()+str(record.get("year", ""))).encode()).hexdigest()[:24]}'
    return dict(pmid=uid, title=title, abstract=str(record.get('abstract') or ''),
                year=str(record.get('year') or ''), journal=str(record.get('journal') or ''),
                doi=doi, authors=str(record.get('authors') or ''), url=str(record.get('url') or (f'https://doi.org/{doi}' if doi else '')),
                source=source, source_id=external or pmid or uid)


def search_embase(query, limit, api_key, insttoken=''):
    """API oficial; exige autorização de Embase concedida pela Elsevier."""
    if not api_key.strip():
        raise ValueError('Informe a chave da API Elsevier com acesso autorizado à Embase.')
    headers={'Accept':'application/json','X-ELS-APIKey':api_key.strip()}
    if insttoken.strip():
        headers['X-ELS-Insttoken']=insttoken.strip()
    result=[]
    total=0
    for offset in range(1,limit+1,25):
        response=requests.get('https://api.elsevier.com/content/embase/article',
                              headers=headers,params={'query':query,'start':offset,'count':min(25,limit-offset+1)},timeout=60)
        if response.status_code in (401,403):
            raise PermissionError('A Elsevier negou acesso à API Embase. A chave requer permissão específica para este produto.')
        response.raise_for_status()
        data=response.json()
        block=data.get('search-results',data)
        total=int(block.get('opensearch:totalResults',0) or 0)
        entries=block.get('entry',[])
        if isinstance(entries,dict):
            entries=[entries]
        if not entries:
            break
        for entry in entries:
            ids=entry.get('dc:identifier','')
            accession=_text(entry.get('embase:accession-number') or entry.get('eid') or ids)
            accession=accession.split(':')[-1] if accession else ''
            title=_text(entry.get('dc:title') or entry.get('title'))
            abstract=_text(entry.get('dc:description') or entry.get('prism:description') or entry.get('abstract'))
            pubdate=_text(entry.get('prism:coverDate') or entry.get('prism:coverDisplayDate'))
            year=re.search(r'\b(?:19|20)\d{2}\b',pubdate)
            record=_normalize(dict(title=title,abstract=abstract,year=year.group() if year else '',
                         journal=_text(entry.get('prism:publicationName')),doi=_text(entry.get('prism:doi')),
                         authors=_text(entry.get('dc:creator') or entry.get('author')),
                         external_id=accession,url=_text(entry.get('prism:url'))), 'Embase',len(result))
            if record:
                result.append(record)
        if len(entries)<min(25,limit-offset+1):
            break
    return result[:limit],total


def parse_ris(content,source):
    text=content.decode('utf-8-sig',errors='replace')
    entries=[]
    current={}
    last=''
    for line in text.splitlines():
        match=re.match(r'^([A-Z][A-Z0-9])\s+-\s+(.*)$',line)
        if match:
            tag,value=match.groups()
            if tag=='TY' and current:
                entries.append(current);current={}
            if tag=='ER':
                entries.append(current);current={};last='';continue
            current.setdefault(tag,[]).append(value.strip());last=tag
        elif line.startswith((' ','\t')) and last and current.get(last):
            current[last][-1]+=' '+line.strip()
    if current:
        entries.append(current)
    rows=[]
    for i,e in enumerate(entries):
        def get(*tags):
            return next((e[t][0] for t in tags if e.get(t)), '')
        year=get('PY','Y1','DA')
        match=re.search(r'\b(?:19|20)\d{2}\b',year)
        rows.append(_normalize(dict(title=get('TI','T1','CT'),abstract=' '.join(e.get('AB',[]) or e.get('N2',[])),
                    year=match.group() if match else '',journal=get('JO','JF','T2'),doi=get('DO'),
                    authors='; '.join(e.get('AU',[]) or e.get('A1',[])),
                    external_id=get('AN','ID','CN'),url=get('UR')),source,i))
    return [r for r in rows if r]


def parse_csv(content,source):
    text=content.decode('utf-8-sig',errors='replace')
    sample=text[:4096]
    try:
        dialect=csv.Sniffer().sniff(sample,delimiters=',;\t')
        reader=csv.DictReader(io.StringIO(text),dialect=dialect)
    except csv.Error:
        reader=csv.DictReader(io.StringIO(text))
    rows=[]
    def get(row,*keys):
        lowered={str(k).lower().strip():v for k,v in row.items() if k}
        return next((str(lowered[k]).strip() for k in keys if lowered.get(k)), '')
    for i,r in enumerate(reader):
        record=_normalize(dict(title=get(r,'title','article title','titulo','título','ti'),
            abstract=get(r,'abstract','resumo','ab'),year=get(r,'year','publication year','ano','py'),
            journal=get(r,'journal','source','publication title','periódico','periodico'),
            doi=get(r,'doi'),authors=get(r,'authors','author','autores','autor','au'),external_id=get(r,'accession number','accession','id','record id','an'),
            pubmed_id=get(r,'pmid','pubmed id'),url=get(r,'url','link')),source,i)
        if record:rows.append(record)
    return rows



def parse_nbib(content, source='PubMed'):
    """Lê exportações PubMed MEDLINE (.nbib), incluindo resumos multilinha."""
    text=content.decode('utf-8-sig', errors='replace')
    entries=[]
    current={}
    last=None
    for line in text.splitlines():
        match=re.match(r'^([A-Z][A-Z0-9]{1,3})\s*-\s*(.*)$', line)
        if match:
            tag,value=match.groups()
            if tag=='PMID' and current:
                entries.append(current)
                current={}
            current.setdefault(tag,[]).append(value.strip())
            last=tag
        elif line.startswith((' ', '\t')) and last and current.get(last):
            current[last][-1]+=' '+line.strip()
        elif not line.strip():
            last=None
    if current:
        entries.append(current)
    rows=[]
    for i,e in enumerate(entries):
        def get(*tags):
            return next((e[t][0] for t in tags if e.get(t)), '')
        year=get('DP','DEP','EDAT')
        found=re.search(r'\b(?:19|20)\d{2}\b',year)
        doi=''
        for aid in e.get('AID',[]):
            if '[doi]' in aid.lower():
                doi=re.sub(r'\s*\[doi\].*$', '', aid, flags=re.I).strip()
                break
        pmid=get('PMID')
        record=_normalize(dict(title=get('TI'), abstract=' '.join(e.get('AB',[])),
            year=found.group() if found else '',journal=get('JT','TA'),doi=doi,
            authors='; '.join(e.get('FAU',[]) or e.get('AU',[])),
            pubmed_id=pmid,external_id=pmid,
            url=f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/' if pmid else ''),source,i)
        if record:
            rows.append(record)
    return rows


def parse_uploaded_bytes(data, filename, source):
    filename=filename.lower()
    if filename.endswith('.ris'):
        return parse_ris(data,source)
    if filename.endswith('.nbib'):
        return parse_nbib(data,source)
    if filename.endswith(('.csv','.tsv')):
        return parse_csv(data,source)
    raise ValueError('Formato não suportado. Use arquivos .ris, .nbib, .csv ou .tsv.')


def parse_file(uploaded,source):
    return parse_uploaded_bytes(uploaded.getvalue(),uploaded.name,source)
