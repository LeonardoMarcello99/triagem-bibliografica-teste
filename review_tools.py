"""Deduplicação conservadora e métricas auditáveis para demonstração web."""
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from xml.sax.saxutils import escape


def norm_title(value):
    text = unicodedata.normalize('NFKD', str(value or '').casefold())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def norm_doi(value):
    text = str(value or '').strip().lower()
    text = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', text)
    text = re.sub(r'^doi:\s*', '', text)
    return text.strip().rstrip('.,;')


def pubmed_id(record):
    for field in ('pubmed_id', 'pmid'):
        value = str(record.get(field) or '').strip()
        if value.isdigit() and len(value) >= 5:
            return value
    url = str(record.get('url') or '')
    match = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?', url)
    return match.group(1) if match else ''


def _year(record):
    match = re.search(r'\b(?:19|20)\d{2}\b', str(record.get('year') or ''))
    return match.group() if match else ''


def match_reason(a, b):
    """Somente chaves fortes; títulos iguais com anos conflitantes não casam."""
    doi_a, doi_b = norm_doi(a.get('doi')), norm_doi(b.get('doi'))
    if doi_a and doi_a == doi_b:
        return 'DOI idêntico'
    pmid_a, pmid_b = pubmed_id(a), pubmed_id(b)
    if pmid_a and pmid_a == pmid_b:
        return 'PMID idêntico'
    ta, tb = norm_title(a.get('title')), norm_title(b.get('title'))
    ya, yb = _year(a), _year(b)
    if ta and ta == tb and len(ta) >= 20 and ya == yb:
        return 'Título normalizado idêntico'
    return None


def _quality(record):
    return (bool(record.get('abstract')), bool(record.get('doi')),
            bool(pubmed_id(record)), sum(bool(record.get(x)) for x in ('year','journal','url')))


def duplicate_groups(records):
    """Grupos transitivos por DOI/PMID/título; sem O(n²) para matches exatos."""
    n = len(records)
    parent = list(range(n))
    reasons = defaultdict(set)
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(i, j, reason):
        a, b = root(i), root(j)
        if a != b:
            parent[b] = a
        reasons[i].add(reason)
        reasons[j].add(reason)
    seen = {}
    for i, r in enumerate(records):
        keys = []
        doi = norm_doi(r.get('doi'))
        pmid = pubmed_id(r)
        title = norm_title(r.get('title'))
        year = _year(r)
        if doi: keys.append(('doi', doi))
        if pmid: keys.append(('pmid', pmid))
        # Para títulos, ano desconhecido requer verificação adicional por índice de título.
        if title and len(title) >= 20:
            keys.append(('title', title, year))
        for key in keys:
            if key in seen:
                j = seen[key]
                reason = match_reason(records[j], r)
                if reason:
                    union(j, i, reason)
            else:
                seen[key] = i
    groups = defaultdict(list)
    for i in range(n):
        groups[root(i)].append(i)
    result = []
    for members in groups.values():
        if len(members) < 2:
            continue
        # Escolhe automaticamente o registro com mais metadados, desempate estável.
        keeper = max(members, key=lambda i: (_quality(records[i]), -i))
        result.append({'members': members, 'keeper': keeper,
                       'reasons': sorted(set().union(*(reasons[i] for i in members)))})
    return sorted(result, key=lambda g: min(g['members']))


def suggest_similar(records, cutoff=0.92, max_comparisons=50000):
    """Sugestões, sem exclusão automática. Comparações bloqueadas por ano/prefixo."""
    buckets = defaultdict(list)
    for i, r in enumerate(records):
        title = norm_title(r.get('title'))
        if len(title) >= 25:
            buckets[(_year(r), title[-18:])].append((i, title))
    suggestions = []
    checked = 0
    for values in buckets.values():
        for a in range(len(values)):
            for b in range(a+1, len(values)):
                if checked >= max_comparisons:
                    return suggestions
                checked += 1
                ia, ta = values[a]
                ib, tb = values[b]
                if ta == tb or match_reason(records[ia], records[ib]):
                    continue
                score = SequenceMatcher(None, ta, tb).ratio()
                if score >= cutoff:
                    suggestions.append((ia, ib, round(score, 3)))
    return sorted(suggestions, key=lambda x:-x[2])


def default_exclusions(records, groups):
    """Retorna índices removidos, sem mutar dados brutos."""
    return {i for group in groups for i in group['members'] if i != group['keeper']}


def prisma_counts(total, duplicates, screened_excluded=0, sought_missing=0,
                  fulltext_excluded=0, included=None):
    """Modelo PRISMA 2020 simplificado para bases de dados, sem inventar etapas."""
    values = (total, duplicates, screened_excluded, sought_missing, fulltext_excluded)
    if any(not isinstance(x, int) or x < 0 for x in values):
        raise ValueError('As contagens devem ser números inteiros não negativos.')
    if duplicates > total:
        raise ValueError('Duplicatas removidas não podem exceder os registros identificados.')
    screened = total - duplicates
    if screened_excluded > screened:
        raise ValueError('Exclusões na triagem excedem os registros disponíveis.')
    sought = screened - screened_excluded
    if sought_missing > sought:
        raise ValueError('Textos completos não recuperados excedem os buscados.')
    assessed = sought - sought_missing
    if fulltext_excluded > assessed:
        raise ValueError('Exclusões após leitura integral excedem os avaliados.')
    remaining = assessed - fulltext_excluded
    if included is not None and (included < 0 or included > remaining):
        raise ValueError('Estudos incluídos não podem exceder os elegíveis.')
    return {'identified':total,'duplicates':duplicates,'screened':screened,
            'screen_excluded':screened_excluded,'sought':sought,
            'not_retrieved':sought_missing,'assessed':assessed,
            'fulltext_excluded':fulltext_excluded,'eligible':remaining,
            'included':included}


def prisma_svg(counts, review_status=None):
    """SVG autocontido para visualização e download, sem serviços externos."""
    boxes = [
        ('Identificação', f"Registros identificados (n = {counts['identified']})", 40, 40),
        ('Remoção', f"Duplicatas removidas (n = {counts['duplicates']})", 435, 40),
        ('Triagem', f"Registros triados (n = {counts['screened']})", 40, 170),
        ('Exclusão', f"Registros excluídos (n = {counts['screen_excluded']})", 435, 170),
        ('Recuperação', f"Relatórios procurados (n = {counts['sought']})", 40, 300),
        ('Não recuperados', f"Não recuperados (n = {counts['not_retrieved']})", 435, 300),
        ('Elegibilidade', f"Relatórios avaliados (n = {counts['assessed']})", 40, 430),
        ('Exclusão integral', f"Excluídos após texto completo (n = {counts['fulltext_excluded']})", 435, 430),
        ('Inclusão', f"Estudos incluídos (n = {counts['included'] if counts['included'] is not None else 'não informado'})", 40, 560),
    ]
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="840" height="820" viewBox="0 0 840 820">',
           '<rect width="840" height="680" fill="white"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#17212d}.head{font-size:15px;font-weight:bold}.body{font-size:13px}</style>']
    for i, (heading, body, x, y) in enumerate(boxes):
        w = 355
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="78" rx="8" fill="#f4f8fc" stroke="#315e89" stroke-width="2"/>')
        out.append(f'<text class="head" x="{x+14}" y="{y+27}">{escape(heading)}</text>')
        out.append(f'<text class="body" x="{x+14}" y="{y+53}">{escape(body)}</text>')
    for y in (118,248,378,508):
        out.append(f'<path d="M217 {y} V{y+50}" stroke="#315e89" stroke-width="2" fill="none"/>')
        out.append(f'<path d="M211 {y+44} L217 {y+52} L223 {y+44}" stroke="#315e89" stroke-width="2" fill="none"/>')
    for y in (79,209,339,469):
        out.append(f'<path d="M395 {y} H435" stroke="#315e89" stroke-width="2" fill="none"/>')
        out.append(f'<path d="M429 {y-6} L437 {y} L429 {y+6}" stroke="#315e89" stroke-width="2" fill="none"/>')
    if review_status is not None:
        # Estados de revisão humana (título/resumo), distintos da inclusão final.
        out.append('<rect x="40" y="655" width="750" height="108" rx="8" fill="#eaf5ff" stroke="#0086D9" stroke-width="2"/>')
        out.append('<text class="head" x="54" y="682">Decisões da revisão humana (triagem preliminar)</text>')
        labels = [('Pendente','Pendentes'), ('Incluir','Incluir'), ('Incerto','Incertos'), ('Excluir','Excluídos')]
        for i,(key,label) in enumerate(labels):
            value=int(review_status.get(key,0))
            out.append(f'<text class="body" x="{54+i*187}" y="715">{escape(label)}: {value}</text>')
        out.append('<text class="body" x="54" y="745">Incluir não significa estudo incluído após avaliação integral.</text>')
    out.append('<text x="40" y="797" font-size="12">Fluxograma simplificado inspirado no PRISMA 2020 — confirmar contagens e motivos antes de publicar.</text>')
    out.append('</svg>')
    return ''.join(out)


def filter_records(records, sources=None, years=None, keywords=''):
    """Filtra registros sem expressões regulares, com AND entre palavras."""
    source_set = None if sources is None else set(sources)
    year_set = set(years or [])
    terms = str(keywords or '').casefold().split()
    output = []
    for record in records:
        if source_set is not None and record.get('source') not in source_set:
            continue
        if year_set and str(record.get('year') or '') not in year_set:
            continue
        searchable = ' '.join(str(record.get(col) or '') for col in
            ('title','abstract','doi','journal','authors','author','pmid')).casefold()
        if all(term in searchable for term in terms):
            output.append(record)
    return output
