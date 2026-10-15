import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).parent
SOURCE=(ROOT/'app.py').read_text(encoding='utf-8')

class WebAppTests(unittest.TestCase):
    def test_all_tabs_match_official(self):
        for name in ['Busca e coleções','Triagem','Duplicatas','Revisão/Filtro','Exportação',
                     'Extração de dados','Fluxograma PRISMA','Backup e restauração de dados']:
            self.assertIn(repr(name),SOURCE)
    def test_ai_tabs_disabled(self):
        tree=ast.parse(SOURCE)
        for name in ['tab2','tab5']:
            tab=next(node for node in tree.body if isinstance(node,ast.With)
                     and any(isinstance(i.context_expr,ast.Name) and i.context_expr.id==name for i in node.items))
            block=ast.get_source_segment(SOURCE,tab)
            self.assertIn('Em desenvolvimento',block)
            self.assertNotIn('.start(',block)
    def test_no_ollama_calls(self):
        self.assertNotIn('ScreeningWorker',SOURCE)
        self.assertNotIn('ExtractionWorker',SOURCE)
        self.assertNotIn('Ollama',SOURCE)
    def test_isolated_db(self):
        db=(ROOT/'db.py').read_text(encoding='utf-8')
        self.assertIn('_session_db_path()',db)
        self.assertIn("st.session_state.get('_litscope_session_db')",db)
        self.assertNotIn('sqlite3.connect(DB_PATH,',db)
    def test_no_local_ai_requirements(self):
        req=(ROOT/'requirements.txt').read_text()
        self.assertNotIn('pymupdf',req)
        self.assertNotIn('reportlab',req)
    def test_session_database_separation(self):
        import sys, types, tempfile
        from unittest.mock import patch
        import db
        with tempfile.TemporaryDirectory() as directory:
            a=str(Path(directory)/'user_a.db')
            b=str(Path(directory)/'user_b.db')
            fake=types.ModuleType('streamlit')
            fake.session_state={'_litscope_session_db':a}
            with patch.dict(sys.modules, {'streamlit':fake}):
                db.create_dataset('Pesquisa A','consulta A',[])
                self.assertEqual(len(db.datasets()),1)
                fake.session_state={'_litscope_session_db':b}
                self.assertEqual(len(db.datasets()),0)
                db.create_dataset('Pesquisa B','consulta B',[])
                self.assertEqual(db.datasets()[0]['name'],'Pesquisa B')
                fake.session_state={'_litscope_session_db':a}
                self.assertEqual(db.datasets()[0]['name'],'Pesquisa A')

    def test_backup_preserves_authors(self):
        from collection_tools import build_backup, read_backup
        record={'pmid':'123','title':'Artigo de teste','authors':'Autora A; Autor B',
                'source':'PubMed','abstract':'Resumo'}
        raw=build_backup({'name':'Teste'},[record],[])
        _,restored,_=read_backup(raw)
        self.assertEqual(restored[0]['authors'],record['authors'])

    def test_review_filters_and_prisma(self):
        from review_tools import filter_records, prisma_counts, prisma_svg
        from prisma_auto import review_status_counts
        rows=[{'pmid':'1','title':'Alzheimer e sono','source':'PubMed','year':'2026','human_label':'Incluir'},
              {'pmid':'2','title':'Cardiologia','source':'Embase','year':'2024','human_label':'Excluir'}]
        self.assertEqual(len(filter_records(rows,keywords='Alzheimer')),1)
        status=review_status_counts(rows)
        self.assertEqual((status['Incluir'],status['Excluir']),(1,1))
        svg=prisma_svg(prisma_counts(2,0,1,0,0,0),review_status=status)
        self.assertIn('svg',svg.lower())

    def test_export_ris_csv(self):
        from collection_tools import csv_bytes, ris_bytes
        rows=[{'pmid':'123','title':'Título exemplo','doi':'10.1000/example'}]
        self.assertIn(b'TY  - JOUR',ris_bytes(rows))
        self.assertIn('Título exemplo',csv_bytes(rows).decode('utf-8-sig'))

    def test_syntax(self):
        for path in ROOT.glob('*.py'):
            ast.parse(path.read_text(encoding='utf-8'),filename=path.name)

if __name__=='__main__':
    unittest.main()
