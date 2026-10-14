"""Versão de validação pública, sem banco de dados nem serviços de IA."""
import io
import re
import time
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

def combine_history(query, op=None):
    current = st.session_state.query.strip()
    if not current:
        st.session_state.query = query
    elif op in ("AND", "OR", "NOT"):
        st.session_state.query = f"({current}) {op} ({query})"

def save_history():
    query = st.session_state.query.strip()
    if query:
        next_id = st.session_state.get("history_next", 1)
        st.session_state.history.insert(0, {
            "id": next_id, "query": query, "time": time.strftime("%H:%M:%S")
        })
        st.session_state.history_next = next_id + 1
        st.session_state.history = st.session_state.history[:100]
        st.session_state.clear_query_next = True

def delete_history(history_id):
    st.session_state.history = [
        h for h in st.session_state.history if h["id"] != history_id
    ]

def article_pubmed_url(article):
    """Oferece link PubMed somente se houver PMID numérico válido."""
    source_id = str(article.get("source_id") or "").strip()
    pmid = str(article.get("pmid") or "").strip()
    if article.get("source") == "PubMed":
        for candidate in (source_id, pmid):
            if re.fullmatch(r"\\d+", candidate):
                return f"https://pubmed.ncbi.nlm.nih.gov/{candidate}/"
    url = str(article.get("url") or "").strip()
    if re.fullmatch(r"https://pubmed\\.ncbi\\.nlm\\.nih\\.gov/\\d+/?", url):
        return url
    return None

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
    if st.session_state.pop("clear_query_next", False):
        st.session_state.query = ""
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
        st.button("ADD", on_click=append_term, args=("AND",),
                  type="primary", use_container_width=True)
        st.caption("Depois de adicionar o primeiro termo, AND, OR e NOT serão liberados.")
    st.text_area("Query (editável)", key="query", height=120)
    st.button("Adicionar consulta ao histórico", disabled=not bool(st.session_state.query.strip()), on_click=save_history)
    if st.session_state.history:
        st.markdown("**Histórico desta sessão**")
        st.caption("Abra ••• para combinar uma consulta salva com a consulta atual.")
        h1, h2, h3, h4 = st.columns([0.8, 1.3, 6, 1])
        for col, title in zip((h1,h2,h3,h4), ("Busca","Actions","Query","Hora")):
            col.markdown(f"**{title}**")
        for item in st.session_state.history:
            cols = st.columns([0.8, 1.3, 6, 1])
            cols[0].write(f"#{item['id']}")
            with cols[1]:
                with st.popover("•••"):
                    if not st.session_state.query.strip():
                        st.button("Add query", key=f"hist_add_{item['id']}",
                                  on_click=combine_history, args=(item["query"],),
                                  use_container_width=True)
                    else:
                        for op in ("AND", "OR", "NOT"):
                            st.button(f"Add with {op}", key=f"hist_{item['id']}_{op}",
                                      on_click=combine_history, args=(item["query"], op),
                                      use_container_width=True)
                    st.button("Delete", key=f"hist_delete_{item['id']}",
                              on_click=delete_history, args=(item["id"],),
                              use_container_width=True)
                    st.button("Create alert", key=f"hist_alert_{item['id']}",
                              disabled=True, use_container_width=True,
                              help="Alertas automáticos não estão disponíveis neste teste.")
            cols[2].code(item["query"], language=None, wrap_lines=True)
            cols[3].write(item["time"])
        if st.button("Limpar histórico", key="clear_history"):
            st.session_state.history = []
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
        visible = view.reset_index(drop=True)
        event = st.dataframe(
            visible, hide_index=True, use_container_width=True,
            on_select="rerun", selection_mode="single-row", key="artigos_web_tabela",
            column_config={
                "url": st.column_config.LinkColumn("Link da fonte", display_text="Abrir")
            } if "url" in visible.columns else None
        )
        selected_rows = event.selection.rows
        if selected_rows:
            st.session_state["selected_article_pmid"] = str(visible.iloc[selected_rows[0]]["pmid"])
        current_id = st.session_state.get("selected_article_pmid")
        chosen = next((r for r in records if str(r["pmid"]) == current_id), None)
        if chosen is None and not visible.empty:
            chosen = visible.iloc[0].to_dict()
        st.caption("Clique em uma linha da tabela para visualizar os dados completos abaixo.")
        if chosen is not None:
            st.divider()
            st.subheader(str(chosen.get("title") or "Artigo sem título"))
            source_name = str(chosen.get("source") or "Não informada")
            source_id = str(chosen.get("source_id") or chosen.get("pmid") or "—")
            st.caption(f"Base: {source_name} | Identificador: {source_id}")
            pubmed_link = article_pubmed_url(chosen)
            if pubmed_link:
                st.link_button("Abrir artigo no PubMed ↗", pubmed_link)
            other_url = str(chosen.get("url") or "").strip()
            if other_url.startswith(("https://", "http://")) and other_url != pubmed_link:
                st.link_button("Abrir na fonte ↗", other_url)
            st.markdown("**Resumo**")
            st.write(str(chosen.get("abstract") or "Resumo indisponível."))
            c_year, c_journal, c_doi = st.columns([1, 3, 2])
            c_year.markdown("**Ano**")
            c_year.write(str(chosen.get("year") or "—"))
            c_journal.markdown("**Periódico**")
            c_journal.write(str(chosen.get("journal") or "—"))
            c_doi.markdown("**DOI**")
            doi = str(chosen.get("doi") or "").strip()
            if doi:
                c_doi.markdown(f"[{doi}](https://doi.org/{doi})")
            else:
                c_doi.write("—")
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
