"""Exportações bibliográficas, estatísticas e backup portátil de coleções."""
import csv
import io
import json
import re
from collections import Counter

BACKUP_FORMAT = 'triagem-principal-colecao-v1'
MAX_BACKUP_BYTES = 25 * 1024 * 1024


def csv_bytes(records):
    output = io.StringIO(newline='')
    fields = ['pmid','title','abstract','year','journal','doi','url','source','source_id',
              'ai_label','ai_reason','human_label','human_note','duplicate_removed']
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue().encode('utf-8-sig')


def _ris_line(tag, value):
    text = str(value or '').replace('\r',' ').replace('\n',' ').strip()
    return f'{tag}  - {text}\r\n' if text else ''


def ris_bytes(records):
    out=[]
    for record in records:
        out.append('TY  - JOUR\r\n')
        for tag,field in [('TI','title'),('AB','abstract'),('PY','year'),('JO','journal'),
                          ('DO','doi'),('UR','url')]:
            out.append(_ris_line(tag,record.get(field)))
        pmid=str(record.get('pmid') or '')
        if pmid.isdigit():
            out.append(_ris_line('AN',pmid))
        out.append('ER  - \r\n\r\n')
    return ''.join(out).encode('utf-8-sig')


def statistics(records):
    return {
        'total':len(records),
        'sources':dict(sorted(Counter(str(r.get('source') or 'Não informada') for r in records).items())),
        'years':dict(sorted(Counter(str(r.get('year') or 'Não informado') for r in records).items())),
        'with_abstract':sum(bool(str(r.get('abstract') or '').strip()) for r in records),
        'with_doi':sum(bool(str(r.get('doi') or '').strip()) for r in records),
        'duplicate_removed':sum(bool(r.get('duplicate_removed')) for r in records),
        'ai_analyzed':sum(bool(r.get('ai_label')) for r in records),
        'human_reviewed':sum(bool(r.get('human_label')) for r in records),
    }


def build_backup(dataset, articles, extractions):
    return json.dumps({
        'format':BACKUP_FORMAT,
        'dataset':{key:dataset.get(key) for key in (
            'name','query','inclusion_criteria','exclusion_criteria','identified_total',
            'prisma_screen_excluded','prisma_not_retrieved','prisma_fulltext_excluded','prisma_included')},
        'articles':articles,
        'extractions':[{k:r.get(k) for k in ('pmid','pdf_name','model','data','verified')}
                       for r in extractions],
    },ensure_ascii=False,indent=2).encode('utf-8')


def read_backup(raw):
    if len(raw)>MAX_BACKUP_BYTES:
        raise ValueError('Backup maior que 25 MB.')
    try:
        data=json.loads(raw)
    except (ValueError,UnicodeDecodeError) as exc:
        raise ValueError('Arquivo JSON inválido.') from exc
    if not isinstance(data,dict) or data.get('format')!=BACKUP_FORMAT:
        raise ValueError('Formato de backup não reconhecido.')
    dataset=data.get('dataset')
    articles=data.get('articles')
    extractions=data.get('extractions')
    if not isinstance(dataset,dict) or not isinstance(articles,list) or not isinstance(extractions,list):
        raise ValueError('Backup incompleto.')
    if len(articles)>100000 or len(extractions)>100000:
        raise ValueError('Backup contém registros demais.')
    allowed={'pmid','title','abstract','year','journal','doi','url','source','source_id','authors',
             'ai_label','ai_reason','ai_criteria','human_label','human_note','reviewed_at',
             'model','criteria_hash','analyzed_at','duplicate_removed'}
    clean=[]
    seen=set()
    for article in articles:
        if not isinstance(article,dict):
            raise ValueError('Registro inválido no backup.')
        record={k:article.get(k) for k in allowed}
        if not isinstance(record.get('pmid'),str) or not record['pmid'] or not isinstance(record.get('title'),str) or not record['title'].strip():
            raise ValueError('Artigo sem identificador ou título válido.')
        if record['pmid'] in seen:
            raise ValueError('Backup contém identificadores repetidos.')
        seen.add(record['pmid'])
        for key in ('abstract','year','journal','doi','url','source','source_id','authors'):
            record[key]=str(record.get(key) or '')
        clean.append(record)
    clean_extractions=[]
    for item in extractions:
        if not isinstance(item,dict) or not isinstance(item.get('pmid'),str) or not isinstance(item.get('data'),dict):
            raise ValueError('Extração inválida no backup.')
        if item['pmid'] not in seen and not item['pmid'].startswith('PDF:'):
            raise ValueError('Extração referencia artigo ausente.')
        clean_extractions.append(item)
    return dataset,clean,clean_extractions
