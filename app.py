"""Versão de validação pública, sem banco de dados nem serviços de IA."""
import io
import re
import pandas as pd
import streamlit as st
from pubmed import search_pubmed, count_pubmed
from sources import FIELDS, add_term, parse_file

st.set_page_config(page_title="Triagem bibliográfica — teste", layout="wide")
st.title("Triagem bibliográfica")
st.caption("Versão de avaliação: busca PubMed, importação bibliográfica e exportação Excel.")
st.warning("Teste temporário: dados ficam somente nesta sessão e podem desaparecer ao atualizar, fechar ou reiniciar o site. Exporte o Excel antes de sair. Não envie informações confidenciais.")
if "articles" not in st.session_state:
    st.session_state.articles = {}
if "history" not in st.session_state:
    st.session_state.history = []
if "query" not in st.session_state:
    st.session_state.query = ""
if "term" not in st.session_state:
    st.session_state.term = ""
if "upload_id" not in st.session_state:
    st.session_state.upload_id = 0
if "preview" not in st.session_state:
    st.session_state.preview = None

def append_term(op):
    term = st.session_state.term.strip()
    if term:
        st.session_state.query = add_term(st.session_state.query, term,
                                           st.session_state.field, op, "PubMed")
        st.session_state.term = ""

def combine_history(query, op):
    current = st.session_state.query.strip()
    st.session_state.query = f"({current}) {op} ({query})" if current else f"({query})"

def save_history():
    query = st.session_state.query.strip()
    if query:
        st.session_state.history.insert(0, query)
        st.session_state.query = ""

def excel_data(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Artigos")
    return output.getvalue()

with st.sidebar:
    st.subheader("Configuração")
    email = st.text_input("Seu e-mail para a NCBI", placeholder="pesquisador@universidade.edu.br")
    st.caption("Usado apenas para identificar solicitações à API PubMed. Não é uma conta nem login.")
    st.info("Cada aba/sessão do navegador mantém seus próprios dados temporários. Não existe cadastro ou armazenamento permanente.")

search_tab, import_tab, results_tab = st.tabs(["Busca PubMed", "Importar arquivos", "Artigos e exportação"])
with search_tab:
    st.subheader("Busca avançada")
    c1, c2 = st.columns([1, 3])
    with c1:
        st.selectbox("Campo", list(FIELDS["PubMed"]), key="field")
    with c2:
        st.text_input("Termo ou expressão", key="term")
    has_query = bool(st.session_state.query.strip())
    if has_query:
        buttons = st.columns(3)
        for col, op in zip(buttons, ("AND", "OR", "NOT")):
            col.button(op, on_click=append_term, args=(op,), use_container_width=True)
    else:
        st.button("ADD", on_click=append_term, args=("AND",))
    st.text_area("Query (editável)", key="query", height=120)
    st.button("Adicionar consulta ao histórico", disabled=not bool(st.session_state.query.strip()), on_click=save_history)
    if st.session_state.history:
        st.markdown("**Histórico desta sessão**")
        for i, item in enumerate(st.session_state.history):
            cols = st.columns([1, 5, 1, 1, 1, 1])
            cols[0].write(f"#{i+1}")
            cols[1].code(item, language=None)
            for col, op in zip(cols[2:5], ("AND", "OR", "NOT")):
                col.button(op, key=f"history_{i}_{op}", on_click=combine_history, args=(item,op), use_container_width=True)
            if cols[5].button("Excluir", key=f"del_{i}"):
                st.session_state.history.pop(i)
                st.rerun()
    st.divider()
    limit = st.number_input("Máximo de artigos para carregar (teste)", min_value=1, max_value=2000, value=100, step=50)
    st.caption("Limite de segurança desta demonstração: 2.000 registros por busca. A API NCBI pode demorar para retornar grandes consultas.")
    if st.button("Buscar no PubMed", type="primary", disabled=not bool(st.session_state.query.strip())):
        if not email or "@" not in email:
            st.error("Informe um e-mail válido na barra lateral.")
        else:
            try:
                with st.spinner("Consultando PubMed..."):
                    records, total = search_pubmed(st.session_state.query, int(limit), email)
                st.session_state.preview = {"query":st.session_state.query, "rows":records, "total":total}
                st.success(f"{total:,} artigos encontrados; {len(records)} carregados para importação.")
            except Exception as exc:
                st.error(f"Falha na consulta: {exc}")
    preview=st.session_state.preview
    if preview:
        st.info(f"Prévia da busca: {len(preview['rows'])} de {preview['total']} artigos.")
        if preview["rows"]:
            st.dataframe(pd.DataFrame(preview["rows"])[["pmid","title","year"]].head(100), hide_index=True, use_container_width=True)
        if st.button("Importar resultados da busca para esta sessão"):
            for record in preview["rows"]:
                st.session_state.articles[record["pmid"]] = {**record, "source":"PubMed"}
            st.success(f"{len(preview['rows'])} registros adicionados. Consulte Artigos e exportação.")

with import_tab:
    st.subheader("Importação de arquivos")
    st.caption("Arquivos RIS, NBIB, CSV ou TSV. Você pode selecionar vários arquivos de uma vez.")
    source=st.selectbox("Base de origem dos arquivos", ["PubMed","Embase","Cochrane","Outra"])
    uploads=st.file_uploader("Selecionar arquivos", type=["ris","nbib","csv","tsv"],
                             accept_multiple_files=True, key=f"uploads_{st.session_state.upload_id}")
    if st.button("Importar arquivos", disabled=not bool(uploads), type="primary"):
        try:
            all_records=[]
            for file in uploads:
                all_records.extend(parse_file(file,source))
            if not all_records:
                st.warning("Nenhum registro válido foi identificado.")
            else:
                for record in all_records:
                    st.session_state.articles[record["pmid"]]=record
                st.session_state.upload_id+=1
                st.success(f"{len(all_records)} registros importados (incluindo possíveis duplicatas).")
                st.rerun()
        except Exception as exc:
            st.error(f"Erro de importação: {exc}")

with results_tab:
    st.subheader("Artigos desta sessão")
    records=list(st.session_state.articles.values())
    st.metric("Artigos disponíveis", len(records))
    if records:
        df=pd.DataFrame(records)
        source_filter=st.multiselect("Filtrar por base", sorted(df["source"].fillna("Desconhecida").unique().tolist()),
                                     default=sorted(df["source"].fillna("Desconhecida").unique().tolist()))
        view=df[df["source"].isin(source_filter)]
        columns=st.multiselect("Colunas para exportar", list(view.columns),
                               default=[x for x in ["pmid","title","abstract","year","journal","doi","url","source"] if x in view.columns])
        st.dataframe(view, hide_index=True, use_container_width=True)
        if columns and not view.empty:
            st.download_button("Exportar Excel", excel_data(view[columns]),
                               file_name="artigos_triagem_teste.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               type="primary")
        if st.button("Limpar os artigos desta sessão"):
            st.session_state.confirm_clear=True
        if st.session_state.get("confirm_clear"):
            st.warning("Deseja apagar todos os artigos desta sessão?")
            a,b=st.columns(2)
            if a.button("Confirmar exclusão"):
                st.session_state.articles={}
                st.session_state.confirm_clear=False
                st.rerun()
            if b.button("Cancelar"):
                st.session_state.confirm_clear=False
                st.rerun()
    else:
        st.info("Faça uma busca no PubMed ou importe arquivos para começar.")
