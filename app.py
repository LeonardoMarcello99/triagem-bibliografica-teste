from pathlib import Path
import tempfile
import uuid
import io
import hashlib
import time
import pandas as pd
import streamlit as st
from db import (connect, datasets, create_dataset, delete_dataset, all_articles,
                save_review, delete_review, save_screening_criteria, save_extraction, get_extractions, verify_extraction, delete_extraction, set_duplicate_removed, set_prisma_manual, restore_collection, update_extraction_field)
from pubmed import search_pubmed
from sources import FIELDS, add_term, parse_file
from review_tools import duplicate_groups, suggest_similar, filter_records, prisma_counts, prisma_svg
from prisma_auto import review_status_counts
from collection_tools import csv_bytes, ris_bytes, statistics, build_backup, read_backup

def add_history_query(source, query, operator=None):
    """Insere uma busca salva; operadores só são permitidos com query existente."""
    key = f'query_{source}'
    current = st.session_state.get(key, '').strip()
    query = query.strip()
    if not query:
        return
    if not current:
        st.session_state[key] = query
    elif operator in ('AND', 'OR', 'NOT'):
        st.session_state[key] = f'({current}) {operator} ({query})'


def add_builder_term(source, operator=None):
    """Atualiza o text_area via callback antes de ele ser instanciado no rerun."""
    key = f'query_{source}'
    current = st.session_state.get(key, '').strip()
    term = st.session_state.get(f'term_{source}', '')
    field = st.session_state.get(f'field_{source}', 'Todos os campos')
    if not term.strip():
        st.session_state[f'notice_{source}'] = 'Informe um termo de pesquisa.'
        return
    st.session_state[key] = add_term(current, term, field, operator or 'AND', source)
    st.session_state[f'term_{source}'] = ''
    st.session_state.pop(f'notice_{source}', None)


def save_search_history(source, query, count=None):
    history = st.session_state.setdefault(f'history_{source}', [])
    next_id = st.session_state.get(f'history_next_{source}', 1)
    st.session_state[f'history_next_{source}'] = next_id + 1
    history.insert(0, {'id': next_id, 'query': query, 'count': count,
                       'time': time.strftime('%H:%M:%S')})
    del history[100:]
    st.session_state[f'clear_query_next_{source}'] = True


def to_excel(df):
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as writer:
        df.to_excel(writer,index=False,sheet_name='Triagem')
    return out.getvalue()

st.set_page_config(page_title='LitScope | Revisão Científica', page_icon=str(Path(__file__).parent / 'favicon.png'), layout='wide', initial_sidebar_state='expanded')

# Personalização visual da aplicação local: tema claro e cor institucional.
# A barra técnica do Streamlit é escondida na interface, sem controle de acesso.
st.markdown("""
<style>
  [data-testid="stToolbar"],
  [data-testid="stDecoration"],
  [data-testid="stStatusWidget"],
  #MainMenu,
  footer { display: none !important; }
  :root {
    color-scheme: light !important;
    --background-color: #FFFFFF;
    --secondary-background-color: #F0F7FC;
    --text-color: #17324A;
    --primary-color: #0086D9;
  }
  html, body, [data-testid="stAppViewContainer"], .stApp,
  [data-testid="stMain"], [data-testid="stMainBlockContainer"] {
    background-color: #FFFFFF !important;
    color: #17324A !important;
  }
  /* Força legibilidade mesmo se o visitante tiver preferência por modo escuro. */
  [data-testid="stMain"] p, [data-testid="stMain"] label,
  [data-testid="stMain"] h1, [data-testid="stMain"] h2,
  [data-testid="stMain"] h3, [data-testid="stMain"] h4,
  [data-testid="stMain"] span:not([data-baseweb="tag"] *),
  [data-testid="stMain"] [data-testid="stMarkdownContainer"] {
    color: #17324A;
  }
  [data-testid="stSidebar"], [data-testid="stSidebarContent"] {
    background-color: #F0F7FC !important;
    color: #17324A !important;
  }
  [data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] span { color: #17324A !important; }
  div[data-baseweb="input"], div[data-baseweb="select"],
  div[data-baseweb="textarea"], div[data-baseweb="base-input"],
  [data-testid="stNumberInput"] input,
  [data-testid="stTextInput"] input,
  [data-testid="stTextArea"] textarea {
    background-color: #F0F7FC !important;
    color: #17324A !important;
  }
  input, textarea { color: #17324A !important; caret-color: #17324A !important; }
  input::placeholder, textarea::placeholder { color: #64748B !important; opacity: 1; }
  [data-baseweb="popover"], [role="listbox"], [role="option"] {
    background-color: #FFFFFF !important;
    color: #17324A !important;
  }
  [data-testid="stTabs"] [role="tab"] { color: #17324A !important; }
  [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #0086D9 !important;
    border-bottom-color: #0086D9 !important;
  }
  [data-testid="stDataFrame"], [data-testid="stTable"] {
    background-color: #FFFFFF !important;
  }
  [data-testid="stExpander"] details, [data-testid="stExpander"] summary {
    background-color: #F0F7FC !important;
    color: #17324A !important;
  }
  [data-testid="stWidgetLabel"] { color: #17324A !important; }

  /* Botão nativo para reabrir a barra lateral após recolhê-la. */
  [data-testid="stSidebarCollapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 999999 !important;
  }
  [data-testid="stSidebarCollapsedControl"] button {
    display: inline-flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    color: #17324A !important;
    background-color: #F0F7FC !important;
    border: 1px solid #B5CEDF !important;
    border-radius: 8px !important;
  }
  [data-testid="stSidebarCollapsedControl"] button svg {
    color: #17324A !important;
    stroke: #17324A !important;
  }
  [data-testid="stSidebar"] button[data-testid="stSidebarCollapseButton"] {
    color: #17324A !important;
  }

  .stButton > button[kind="primary"],
  .stDownloadButton > button[kind="primary"],
  button[data-testid="stBaseButton-primary"] {
    background-color: #0086D9 !important;
    border-color: #0086D9 !important;
    color: #FFFFFF !important;
  }
  .stButton > button[kind="primary"]:hover,
  .stDownloadButton > button[kind="primary"]:hover,
  button[data-testid="stBaseButton-primary"]:hover {
    background-color: #006FB5 !important;
    border-color: #006FB5 !important;
  }
  .stButton > button[kind="primary"] *,
  .stDownloadButton > button[kind="primary"] *,
  button[data-testid="stBaseButton-primary"] * {
    color: #FFFFFF !important;
  }
  a, a:visited { color: #0086D9 !important; }
</style>
""", unsafe_allow_html=True)

# Banco SQLite separado por sessão: visitantes não compartilham coleções nem revisões.
# Os arquivos são temporários no servidor, não armazenamento permanente.
if '_litscope_session_db' not in st.session_state:
    session_dir = Path(tempfile.gettempdir()) / 'litscope_web_sessions'
    session_dir.mkdir(parents=True, exist_ok=True)
    st.session_state['_litscope_session_db'] = str(session_dir / f'{uuid.uuid4().hex}.db')
connect().close()
st.title('LitScope')
st.caption('Plataforma de revisão científica | Organize referências, revise estudos e acompanhe evidências em um único ambiente.')
st.info('Versão web de demonstração. Seus dados são temporários e exclusivos desta sessão. Faça backup ou exporte sua coleção antes de sair.')
with st.sidebar:
    email=st.text_input('E-mail NCBI')
    st.caption('Coleções temporárias por sessão. Para guardar seu trabalho, utilize Backup e restauração de dados.')

bases=datasets()
options={f"{d['name']} (#{d['id']}, {d['total']} artigos)":d['id'] for d in bases}
CREATE_OPTION='＋ Criar nova coleção'
collection_choices=list(options)+[CREATE_OPTION]
selected=st.selectbox('Coleção de artigos ativa',collection_choices,index=0 if options else len(collection_choices)-1,
                      key='active_collection_selector',
                      help='Selecione uma coleção existente ou escolha Criar nova coleção para abrir o formulário.')
did=options.get(selected)
running={'running':False}

tab1,tab2,tab6,tab3,tab4,tab5,tab7,tab8=st.tabs(['Busca e coleções','Triagem','Duplicatas','Revisão/Filtro','Exportação','Extração de dados','Fluxograma PRISMA','Backup e restauração de dados'])
with tab1:
    if did is not None:
        st.info('Você está utilizando uma coleção existente. Para criar outra, selecione **＋ Criar nova coleção** no campo **Coleção de artigos ativa** acima.')
    if st.session_state.get('last_delete_message'):
        st.success(st.session_state.pop('last_delete_message'))
    if did is None:
        st.subheader('Criar nova coleção')
        name=st.text_input('Nome da nova coleção',placeholder='Alzheimer — PubMed e Embase')
        st.selectbox('Bases de dados', ['PubMed'], index=0,
            help='Busca integrada disponível somente para PubMed. Embase e Cochrane podem ser importadas por arquivo.')
        selected_sources=['PubMed']
        all_articles_mode = st.checkbox('Buscar todos os artigos encontrados no PubMed', value=True,
            help='Padrão: todos. Para consultas grandes, a busca pode levar bastante tempo e consumir memória.')
        limit = None if all_articles_mode else int(st.number_input(
            'Máximo de artigos por busca no PubMed', min_value=1, max_value=100000, value=1500, step=100))
        limit_key = 'todos' if all_articles_mode else limit
        queries={}
        for source in selected_sources:
            if st.session_state.pop(f'clear_query_next_{source}', False):
                st.session_state[f'query_{source}'] = ''
            with st.container(border=True):
                st.markdown(f'#### Busca — {source}')
                st.markdown('**Adicionar termos à consulta**')
                col1,col2=st.columns([1,3])
                with col1:
                    field=st.selectbox('Campo',list(FIELDS[source]),key=f'field_{source}')
                with col2:
                    term=st.text_input('Termo ou expressão',placeholder='Ex.: Alzheimer Disease',key=f'term_{source}')
                has_query = bool(st.session_state.get(f'query_{source}', '').strip())
                if not has_query:
                    st.button('ADD', key=f'add_first_{source}', type='primary',
                              on_click=add_builder_term, args=(source,), use_container_width=True)
                else:
                    ops=st.columns(3)
                    for col, op in zip(ops, ['AND','OR','NOT']):
                        col.button(f'Adicionar com {op}', key=f'add_{source}_{op}',
                                   on_click=add_builder_term, args=(source, op),
                                   use_container_width=True)
                if st.session_state.get(f'notice_{source}'):
                    st.warning(st.session_state[f'notice_{source}'])
                queries[source]=st.text_area('Query (editável)',key=f'query_{source}',height=110,
                    placeholder='Use os botões acima ou digite a consulta manualmente.')
                search_col, _ = st.columns([1, 3])
                with search_col:
                    do_search = st.button('Buscar', key=f'buscar_{source}', type='primary',
                                          use_container_width=True, disabled=(source != 'PubMed'),
                                          help='Executa a consulta no PubMed e apresenta os resultados sem importar.')
                if do_search:
                    query = queries.get('PubMed', '').strip()
                    if 'PubMed' not in selected_sources or not query:
                        st.warning('Para buscar, selecione PubMed e informe uma consulta.')
                    elif not email or '@' not in email:
                        st.warning('Informe um e-mail NCBI válido na barra lateral.')
                    else:
                        try:
                            with st.spinner('Buscando artigos no PubMed...'):
                                rows, count = search_pubmed(query, limit, email)
                            for row in rows:
                                row['source'] = 'PubMed'
                                row['source_id'] = row['pmid']
                            st.session_state['pubmed_preview'] = {
                                'query': query, 'limit': limit_key, 'rows': rows, 'count': count
                            }
                            st.success(f'Busca concluída: {count} resultado(s) encontrados; {len(rows)} carregados para importação.')
                        except Exception as exc:
                            st.session_state.pop('pubmed_preview', None)
                            st.error(f'Erro ao buscar no PubMed: {exc}')

                preview = st.session_state.get('pubmed_preview')
                if preview:
                    if preview['query'] == queries.get('PubMed', '').strip() and preview['limit'] == limit_key:
                        st.info(f"Busca disponível para importação: {len(preview['rows'])} artigo(s) de {preview['count']} resultado(s).")
                        if preview['rows']:
                            st.dataframe(pd.DataFrame(preview['rows'])[['title','pmid']].head(20),
                                         hide_index=True, use_container_width=True)
                    else:
                        st.warning('A consulta ou o limite foi alterado desde a última busca. Clique em Buscar novamente antes de importar.')

                if source == 'PubMed' and preview and preview['query'] == queries.get('PubMed', '').strip() and preview['limit'] == limit_key:
                    st.markdown('#### Adicionar resultados da busca')
                    st.caption('Cria uma nova coleção somente com os artigos encontrados no PubMed. Não utiliza arquivos anexados.')
                    if st.button('Adicionar artigos da busca', key='add_pubmed_search_collection',
                                 type='primary', use_container_width=False,
                                 disabled=not bool(preview['rows'])):
                        if not name.strip():
                            st.error('Informe o nome da nova coleção acima antes de adicionar os artigos.')
                        else:
                            unique = {r['pmid']: r for r in preview['rows']}
                            new_id = create_dataset(name.strip(), f'[PubMed] {preview["query"]}',
                                                    list(unique.values()), identified_total=len(preview['rows']))
                            st.session_state['last_import_message'] = (
                                f'Coleção #{new_id} criada a partir da busca PubMed com {len(unique)} artigos.')
                            st.session_state.pop('pubmed_preview', None)
                            st.rerun()

                st.markdown('#### Histórico de pesquisas — ' + source)
                query_now = st.session_state.get(f'query_{source}', '').strip()
                col_hist1, col_hist2 = st.columns([2, 1])
                with col_hist1:
                    if st.button('Adicionar consulta ao histórico', key=f'history_save_{source}',
                                 disabled=not bool(query_now)):
                        try:
                            count = None
                            if source == 'PubMed' and email and '@' in email:
                                from pubmed import count_pubmed
                                with st.spinner('Consultando total de resultados no PubMed...'):
                                    count = count_pubmed(query_now, email)
                            save_search_history(source, query_now, count)
                            st.rerun()
                        except Exception as exc:
                            st.error(f'Não foi possível consultar o PubMed: {exc}')
                with col_hist2:
                    if st.button('Limpar histórico', key=f'history_clear_{source}',
                                 disabled=not st.session_state.get(f'history_{source}')):
                        st.session_state[f'history_{source}'] = []
                        st.rerun()
                history = st.session_state.get(f'history_{source}', [])
                if not history:
                    st.info('Nenhuma consulta no histórico. Monte uma query e clique em Adicionar consulta ao histórico.')
                else:
                    h1, h2, h3, h4, h5 = st.columns([0.6, 1.2, 5, 1.3, 1])
                    for col, title in zip([h1, h2, h3, h4, h5],
                                          ['Busca', 'Actions', 'Query', 'Resultados', 'Hora']):
                        col.markdown('**' + title + '**')
                    for item in history:
                        c1, c2, c3, c4, c5 = st.columns([0.6, 1.2, 5, 1.3, 1])
                        c1.write(f"#{item['id']}")
                        with c2:
                            with st.popover('•••'):
                                # Recalcular a cada rerun: consulta vazia só permite Add query.
                                if not st.session_state.get(f'query_{source}', '').strip():
                                    st.button('Add query', key=f"hist_add_{source}_{item['id']}",
                                              on_click=add_history_query,
                                              args=(source, item['query']),
                                              use_container_width=True)
                                else:
                                    for operator, label in [('AND', 'Add with AND'),
                                                            ('OR', 'Add with OR'),
                                                            ('NOT', 'Add with NOT')]:
                                        st.button(label, key=f"hist_{source}_{item['id']}_{operator}",
                                                  on_click=add_history_query,
                                                  args=(source, item['query'], operator),
                                                  use_container_width=True)
                                if st.button('Delete', key=f"remove_{source}_{item['id']}",
                                             use_container_width=True):
                                    st.session_state[f'history_{source}'] = [
                                        row for row in st.session_state[f'history_{source}']
                                        if row['id'] != item['id']]
                                    st.rerun()
                                st.button('Create alert', key=f"alert_{source}_{item['id']}",
                                          use_container_width=True, disabled=True,
                                          help='Alertas automáticos ainda não estão disponíveis.')
                        c3.code(item['query'], language=None, wrap_lines=True)
                        c4.write(f"{item['count']:,}" if item['count'] is not None else '—')
                        c5.write(item['time'])
                if source=='Cochrane':
                    st.info('A consulta é para executar manualmente na Cochrane Library. Depois exporte os resultados em RIS ou CSV e importe abaixo.')
                if source=='Embase':
                    st.caption('Para descritores Emtree, confirme a grafia e sintaxe na Embase. A consulta pode ser ajustada manualmente.')
        with st.expander('Importar a partir de arquivos', expanded=False):
            st.markdown('### Importar artigos de arquivos')
            if 'upload_generation' not in st.session_state:
                st.session_state['upload_generation'] = 0
            uploaded_files=st.file_uploader('Escolha os arquivos para importar',
                type=['ris','nbib','csv','tsv'],accept_multiple_files=True,
                key=f"arquivos_importacao_{st.session_state['upload_generation']}")
            source_by_file={}
            for index,uploaded in enumerate(uploaded_files or []):
                default_source='PubMed' if uploaded.name.lower().endswith('.nbib') else 'Embase'
                source_by_file[index]=st.selectbox(f'Base de origem — {uploaded.name}',
                    ['PubMed','Embase','Cochrane','Outra'],
                    index=['PubMed','Embase','Cochrane','Outra'].index(default_source),
                    key=f'origem_{index}_{uploaded.name}')
            import_col, _ = st.columns([1, 3])
            with import_col:
                importar=st.button('Importar arquivos', type='primary', use_container_width=True,
                                   disabled=not bool(uploaded_files),
                                   help='Cria uma coleção exclusivamente com os arquivos selecionados.')
            if importar:
                if not name.strip():
                    st.error('Informe um nome para a coleção.')
                else:
                    combined = []
                    report = []
                    errors = []
                    for index, uploaded in enumerate(uploaded_files or []):
                        source = source_by_file[index]
                        try:
                            rows = parse_file(uploaded, source)
                            combined.extend(rows)
                            report.append(f'{uploaded.name} ({source}): {len(rows)} artigos')
                            if not rows:
                                errors.append(f'{uploaded.name}: nenhum registro com título identificado')
                        except Exception as exc:
                            errors.append(f'{uploaded.name}: {exc}')
                    for msg in errors:
                        st.error(msg)
                    if combined and not errors:
                        unique = {r['pmid']: r for r in combined}
                        strategy = 'Arquivos: ' + ', '.join(
                            f'{u.name} ({source_by_file[i]})' for i, u in enumerate(uploaded_files or [])
                        )
                        new_id = create_dataset(name.strip(), strategy, list(unique.values()),
                                                identified_total=len(combined))
                        st.session_state['last_import_message'] = (
                            f'Coleção #{new_id} criada com {len(unique)} registros importados de arquivos. '
                            + '; '.join(report)
                        )
                        st.session_state['upload_generation'] += 1
                        st.rerun()
                    elif combined:
                        st.warning('A coleção não foi criada porque uma ou mais fontes falharam.')
                    elif not errors:
                        st.warning('Nenhum artigo disponível. Selecione arquivos antes de importar.')
    if st.session_state.get('last_import_message'):
        message=st.session_state.pop('last_import_message')
        st.success(message)
        st.toast(message, icon='🔔')
    if did is not None:
        st.subheader('Excluir coleção')
        st.write('Exclusão permanente da coleção selecionada e suas decisões de triagem. Outras coleções permanecem intactas.')
        # Confirmação em duas etapas: checkbox + diálogo modal com ação explícita.
        # O estado da checkbox é sempre limpo após o clique em Excluir coleção.
        if 'delete_ack_generation' not in st.session_state:
            st.session_state['delete_ack_generation'] = 0

        @st.dialog('Confirmar exclusão permanente')
        def confirm_dataset_deletion(dataset_id, dataset_name):
            st.warning('Esta operação não pode ser desfeita.')
            st.write(f'Você está prestes a excluir a coleção **{dataset_name}** (#{dataset_id}) e todas as decisões de triagem dessa coleção.')
            st.write('Tem certeza de que deseja continuar?')
            left, right = st.columns(2)
            with left:
                if st.button('Cancelar', use_container_width=True, key='cancelar_exclusao'):
                    st.rerun()
            with right:
                if st.button('Sim, excluir permanentemente', type='primary',
                             use_container_width=True, key='confirmar_exclusao_final'):
                    # Evitar excluir outra coleção se a seleção mudar durante a confirmação.
                    if False:  # Triagem automática indisponível nesta versão web
                        st.error('Não é possível excluir enquanto houver triagem em andamento.')
                    else:
                        delete_dataset(dataset_id)
                        st.session_state['delete_ack_generation'] += 1
                        st.session_state['last_delete_message'] = f'Coleção {dataset_name} excluída.'
                        st.rerun()

        confirm=st.checkbox('Confirmo que quero excluir a coleção selecionada e seus resultados.',
                            key=f"delete_ack_{did}_{st.session_state['delete_ack_generation']}")
        if st.button('Excluir coleção',disabled=not confirm or running['running']):
            # Desmarcar mesmo se a exclusão for cancelada no diálogo.
            st.session_state['delete_ack_generation'] += 1
            current_name=next((d['name'] for d in bases if d['id']==did),str(did))
            confirm_dataset_deletion(did,current_name)
    else:
        st.info('Nenhuma coleção cadastrada.')

with tab2:
    st.subheader('Triagem')
    st.info('Em desenvolvimento')

with tab3:
    if did is None:
        st.info('Selecione uma coleção.')
    else:
        articles=all_articles(did)
        if not articles:
            st.info('Coleção vazia.')
        else:
            df=pd.DataFrame(articles)
            analyzed=df[df['ai_label'].notna()]
            st.metric('Artigos analisados e disponíveis agora',len(analyzed))
            with st.expander('Pesquisar e filtrar artigos para revisão',expanded=True):
                q=st.text_input('Pesquisar em título, resumo, autores, periódico, DOI ou identificador',key=f'review_query_{did}')
                sources=sorted({str(r.get('source') or 'Não informada') for r in articles})
                selected_sources=st.multiselect('Base de origem',sources,default=sources,key=f'review_sources_{did}')
                years=sorted({str(r.get('year')) for r in articles if r.get('year')},reverse=True)
                selected_years=st.multiselect('Ano (vazio = todos)',years,key=f'review_years_{did}')
                show_duplicates=st.checkbox('Incluir artigos marcados como duplicatas',value=False,key=f'review_duplicates_{did}')
                human_filter=st.selectbox('Decisão humana',['Todos','Pendente','Incluir','Excluir','Incerto'],key=f'review_human_{did}')
                only=st.checkbox('Mostrar somente artigos já analisados pela IA',value=False,key=f'review_only_ai_{did}')
                filt=st.selectbox('Classificação IA',['Todos','Potencialmente elegível','Provavelmente inelegível','Incerto','Não analisado'],key=f'review_ai_{did}')
            filtered=filter_records(articles,sources=selected_sources,years=selected_years,keywords=q)
            filtered=[r for r in filtered if (show_duplicates or not r.get('duplicate_removed'))
                and (human_filter=='Todos' or (human_filter=='Pendente' and r.get('human_label') in (None,'','Pendente')) or r.get('human_label')==human_filter)
                and (not only or r.get('ai_label'))
                and (filt=='Todos' or (filt=='Não analisado' and not r.get('ai_label')) or r.get('ai_label')==filt)]
            view=pd.DataFrame(filtered,columns=df.columns)
            st.caption(f'{len(view)} artigo(s) correspondem aos filtros atuais.')
            if not view.empty:
                st.download_button('Exportar resultados filtrados (Excel)',to_excel(view),
                    file_name=f'colecao_{did}_revisao_filtrada.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    key=f'review_export_{did}')
            # Seleção por clique em qualquer célula da linha (PMID ou título inclusive).
            # Mantemos o PMID em session_state para não perder a escolha em reruns.
            visible = view[['source','source_id','pmid','title','year','ai_label','ai_reason','human_label']].reset_index(drop=True)
            event = st.dataframe(
                visible, use_container_width=True, hide_index=True,
                on_select='rerun', selection_mode='single-row', key=f'artigos_tabela_{did}'
            )
            chosen = event.selection.rows
            # Streamlit pode preservar um índice de seleção anterior após o filtro.
            # Só acessar a linha se o índice existir na tabela atual.
            visible_pmids = set(visible['pmid'].astype(str))
            if chosen and 0 <= chosen[0] < len(visible):
                st.session_state[f'pmid_revisao_{did}'] = str(visible.iloc[chosen[0]]['pmid'])
            current_pmid = st.session_state.get(f'pmid_revisao_{did}')
            pmid = current_pmid if current_pmid in visible_pmids else None
            if pmid is None:
                st.session_state.pop(f'pmid_revisao_{did}', None)
                if not visible.empty:
                    pmid = str(visible.iloc[0]['pmid'])
            if visible.empty:
                st.info('Nenhum artigo corresponde aos filtros selecionados.')
            st.caption('Clique em uma linha da tabela, no PMID ou no título, para abrir o artigo abaixo.')
            if pmid:
                a=df[df['pmid'].astype(str)==str(pmid)].iloc[0]
                st.subheader(a['title'])
                st.write('**Autores:**', a.get('authors') or 'Não informado')
                if a['url']:
                    st.markdown(f"[Abrir artigo na fonte]({a['url']})")
                st.caption(f"Base: {a['source']} | Identificador: {a['source_id']}")
                st.write('**Resumo:**',a['abstract'] or 'Indisponível')
                st.write('**IA:**',a['ai_label'] or 'Não analisado')
                st.write('**Justificativa:**',a['ai_reason'] or '—')
                labels=['Pendente','Incluir','Excluir','Incerto']
                current=a['human_label'] if a['human_label'] in labels else 'Pendente'
                decision=st.selectbox('Decisão humana',labels,index=labels.index(current),key=f'decisao_{did}_{pmid}')
                note=st.text_area('Observações',value=a['human_note'] or '',key=f'nota_{did}_{pmid}')
                if st.button('Salvar revisão'):
                    save_review(did,pmid,decision,note)
                    st.toast('Revisão salva com sucesso.', icon='✅')
                    st.success('Revisão salva.')
                    st.rerun()
                if a['reviewed_at'] is not None:
                    with st.expander('Excluir revisão humana salva', expanded=False):
                        st.warning('Apenas a decisão e as observações humanas serão apagadas. O artigo e a análise da IA serão mantidos.')
                        confirm_review=st.checkbox('Confirmo que desejo apagar esta revisão', key=f'delete_review_confirm_{did}_{pmid}')
                        if st.button('Excluir revisão salva', disabled=not confirm_review, key=f'delete_review_{did}_{pmid}'):
                            delete_review(did,pmid)
                            st.toast('Revisão humana excluída.', icon='🗑️')
                            st.rerun()
            if st.button('Atualizar resultados da revisão'):
                st.rerun()

with tab5:
    st.subheader('Extração de dados')
    st.info('Em desenvolvimento')

with tab4:
    if did is None:
        st.info('Selecione uma coleção.')
    else:
        articles_export = all_articles(did)
        if not articles_export:
            st.info('Coleção vazia.')
        df = pd.DataFrame(articles_export, columns=['pmid','source','source_id','title','abstract','year','journal','doi','url','authors','ai_label','ai_reason','ai_criteria','human_label','human_note','reviewed_at','model','criteria_hash','analyzed_at'])
        st.subheader('Exportação personalizada')
        st.caption('Os filtros abaixo afetam somente o Excel, não modificam a coleção nem as decisões salvas.')
        export_only=st.checkbox('Exportar apenas artigos analisados pela IA',value=False,
                                help='Desmarque para permitir incluir artigos ainda não analisados.')
        human_choices=['Pendente','Incluir','Excluir','Incerto']
        chosen_human=st.multiselect(
            'Decisão humana — escolha uma ou mais',
            human_choices, default=human_choices,
            help='Pendente inclui artigos sem revisão humana e artigos marcados como Pendente.'
        )
        ai_choices=['Potencialmente elegível','Provavelmente inelegível','Incerto','Não analisado']
        chosen_ai=st.multiselect(
            'Classificação da IA — escolha uma ou mais (opcional)',
            ai_choices, default=[],
            help='Sem seleção: não filtra pela IA. Pode combinar com o filtro de decisão humana.'
        )
        column_names={
            'pmid':'Identificador interno', 'source':'Base de dados', 'source_id':'ID na base', 'title':'Título', 'abstract':'Resumo', 'year':'Ano',
            'journal':'Periódico', 'doi':'DOI', 'url':'Link do artigo',
            'ai_label':'Classificação IA', 'ai_reason':'Justificativa IA',
            'ai_criteria':'Critérios identificados pela IA',
            'human_label':'Decisão humana', 'human_note':'Observações humanas',
            'reviewed_at':'Data da revisão', 'model':'Modelo IA',
            'criteria_hash':'Identificador dos critérios', 'analyzed_at':'Data da análise'
        }
        defaults=['source','source_id','title','year','ai_label','ai_reason','human_label','human_note']
        selected_columns=st.multiselect(
            'Colunas do Excel',
            options=list(column_names),
            default=defaults,
            format_func=lambda c:column_names[c],
            help='A ordem selecionada é a ordem das colunas na planilha.'
        )
        export_df=df.copy()
        if export_only:
            export_df=export_df[export_df['ai_label'].notna()]
        # NULL representa uma decisão humana ainda pendente.
        if chosen_human:
            human_status=export_df['human_label'].fillna('Pendente')
            export_df=export_df[human_status.isin(chosen_human)]
        else:
            export_df=export_df.iloc[0:0]
        if chosen_ai:
            ai_status=export_df['ai_label'].fillna('Não analisado')
            export_df=export_df[ai_status.isin(chosen_ai)]
        st.write(f'**{len(export_df)} artigo(s)** atendem aos filtros de exportação.')
        if not selected_columns:
            st.warning('Selecione pelo menos uma coluna para exportar.')
        else:
            output=export_df[selected_columns].rename(columns=column_names)
            st.dataframe(output.head(10),use_container_width=True,hide_index=True)
            st.download_button(
                'Exportar Excel com filtros',
                data=to_excel(output),
                file_name=f'triagem_colecao_{did}_filtrada.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                disabled=output.empty
            )


with tab6:
    st.subheader('Identificação e gerenciamento de duplicatas')
    if did is None:
        st.info('Selecione uma coleção para analisar.')
    else:
        rows = all_articles(did)
        if not rows:
            st.info('Coleção vazia.')
        else:
            st.caption('Nenhum registro é apagado automaticamente. A exclusão de duplicatas é uma marcação reversível, independente da triagem por IA e da revisão humana.')
            groups = duplicate_groups(rows)
            suggestions = suggest_similar(rows)
            removed = {str(r['pmid']) for r in rows if r.get('duplicate_removed')}
            a,b,c = st.columns(3)
            a.metric('Registros da coleção',len(rows))
            b.metric('Grupos de duplicatas',len(groups))
            c.metric('Marcados como duplicata',len(removed))
            with st.expander('Analisar duplicatas',expanded=True):
                if not groups:
                    st.success('Nenhum grupo de duplicatas exatas identificado nos registros disponíveis.')
                for gidx, group in enumerate(groups):
                    st.markdown(f"**Grupo {gidx+1}** — {', '.join(group['reasons']) or 'Correspondência por identificador'}")
                    members = group['members']
                    for idx in members:
                        record = rows[idx]
                        pmid = str(record['pmid'])
                        is_removed = pmid in removed
                        cols=st.columns([6,2,2])
                        cols[0].write(f"{record.get('title') or 'Sem título'} — {record.get('source') or 'Fonte desconhecida'} — {record.get('year') or 's/ano'}")
                        cols[1].caption('Marcado como duplicata' if is_removed else ('Sugerido manter' if idx == group['keeper'] else 'Possível duplicata'))
                        if cols[2].button('Restaurar' if is_removed else 'Marcar duplicata',key=f'dup_{did}_{gidx}_{pmid}'):
                            set_duplicate_removed(did,pmid,not is_removed)
                            st.rerun()
                if suggestions:
                    st.markdown('**Títulos semelhantes — conferir manualmente**')
                    st.caption('Sem exclusão automática. Semelhança textual não comprova que sejam o mesmo estudo.')
                    for i,j,score in suggestions[:50]:
                        st.write(f"{score:.0%}: {rows[i]['title']} ↔ {rows[j]['title']}")
                if groups:
                    st.info('Sugestões de qual registro manter são apenas indicativas; revise as fontes antes de marcar. Artigos já marcados continuam disponíveis nas outras abas.')
            if removed:
                removed_rows = [r for r in rows if str(r['pmid']) in removed]
                st.download_button('Exportar duplicatas marcadas (Excel)',to_excel(pd.DataFrame(removed_rows)),file_name=f'colecao_{did}_duplicatas.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key=f'dup_download_{did}')

with tab7:
    st.subheader('Fluxograma PRISMA — visão simplificada')
    if did is None:
        st.info('Selecione uma coleção.')
    else:
        rows=all_articles(did)
        info=next((d for d in bases if d['id']==did),{})
        if not rows:
            st.info('Coleção vazia.')
        else:
            identified=max(int(info.get('identified_total') or len(rows)),len(rows))
            marked_removed=sum(bool(r.get('duplicate_removed')) for r in rows)
            collapsed=max(0,identified-len(rows))
            removed=marked_removed+collapsed
            st.metric('Registros identificados na importação',identified)
            st.metric('Registros removidos antes da triagem',removed)
            available=len(rows)-marked_removed
            status=review_status_counts(rows)
            st.markdown('#### Decisões da revisão humana — atualização automática')
            cols=st.columns(4)
            for col,(label,value) in zip(cols,[
                ('Incluir',status['Incluir']),('Excluir',status['Excluir']),
                ('Incerto',status['Incerto']),('Pendente',status['Pendente'])
            ]):
                col.metric(label,value)
            st.caption('Essas contagens vêm diretamente das decisões salvas na aba Revisão e são atualizadas após cada alteração. Artigos marcados como duplicatas removidas não entram na contagem.')
            screen=status['Excluir']
            st.metric('Excluídos na triagem (automático)',screen)
            st.caption('Para este fluxograma simplificado, decisões humanas "Excluir" são consideradas exclusões na triagem de título/resumo. Não confundir com exclusões após leitura do texto completo.')
            sought=available-screen
            st.markdown('#### Etapas posteriores — preenchimento manual')
            st.caption('A avaliação do texto completo não é registrada como etapa separada nesta versão. Por isso, suas contagens continuam manuais.')
            missing=st.number_input('Relatórios completos não recuperados',min_value=0,max_value=sought,
                value=min(int(info.get('prisma_not_retrieved') or 0),sought),key=f'prisma_missing_{did}')
            assessed=sought-missing
            full=st.number_input('Relatórios excluídos após avaliação integral',min_value=0,max_value=assessed,
                value=min(int(info.get('prisma_fulltext_excluded') or 0),assessed),key=f'prisma_full_{did}')
            possible=assessed-full
            included=st.number_input('Estudos incluídos após avaliação integral (manual)',
                min_value=0,max_value=possible,value=min(int(info.get('prisma_included') or 0),possible),
                key=f'prisma_included_{did}')
            if st.button('Salvar contagens das etapas posteriores',key=f'prisma_save_{did}'):
                set_prisma_manual(did,int(screen),int(missing),int(full),int(included))
                st.success('Contagens manuais posteriores salvas. A contagem da triagem continuará automática.')
            if status['Incerto'] or status['Pendente']:
                st.warning('Fluxograma provisório: existem registros incertos ou pendentes. Resolva as decisões antes de publicar o PRISMA.')
            try:
                counts=prisma_counts(int(identified),int(removed),int(screen),int(missing),int(full),int(included))
                svg=prisma_svg(counts,review_status=status)
                st.image(svg)
                st.download_button('Baixar fluxograma PRISMA (SVG)',svg,file_name=f'prisma_colecao_{did}.svg',mime='image/svg+xml',key=f'prisma_svg_{did}')
                st.download_button('Baixar contagens PRISMA (CSV)',pd.DataFrame([{**counts, **{'revisao_'+k.lower():status[k] for k in ('Pendente','Incluir','Incerto','Excluir')}}]).to_csv(index=False).encode('utf-8-sig'),file_name=f'prisma_colecao_{did}.csv',mime='text/csv',key=f'prisma_csv_{did}')
            except ValueError as exc:
                st.error(f'Contagens incompatíveis: {exc}')
            st.warning('Fluxograma simplificado inspirado no PRISMA 2020; não é substituto da documentação completa de uma revisão sistemática. Confira as contagens antes de publicar.')


with tab8:
    st.subheader('Backup e restauração de dados')
    st.caption('Faça cópias de segurança e restaure coleções. Também estão disponíveis estatísticas e exportação bibliográfica.')
    if did is None:
        st.info('Crie uma coleção ou restaure um backup JSON para começar.')
        restore_first=st.file_uploader('Restaurar coleção a partir de backup JSON', type=['json'],key='restore_initial_backup')
        if restore_first is not None:
            try:
                meta, records, extractions = read_backup(restore_first.getvalue())
                st.write(f"Coleção: {meta.get('name','sem nome')} — {len(records)} artigos")
                confirm_first=st.checkbox('Confirmo que desejo restaurar esta coleção',key='confirm_initial_restore')
                if st.button('Restaurar coleção',disabled=not confirm_first,key='restore_initial_button'):
                    restore_collection(meta,records,extractions)
                    st.success('Coleção restaurada.')
                    st.rerun()
            except (ValueError,TypeError) as exc:
                st.error(f'Backup inválido: {exc}')
    else:
        rows=all_articles(did)
        current_dataset=next((d for d in datasets() if d['id']==did),{})
        st.markdown('**1. Resumo estatístico**')
        stats=statistics(rows)
        m1,m2,m3,m4=st.columns(4)
        m1.metric('Artigos',stats['total'])
        m2.metric('Com resumo',stats['with_abstract'])
        m3.metric('Duplicatas marcadas',stats['duplicate_removed'])
        m4.metric('Com DOI',stats['with_doi'])
        m5,m6=st.columns(2)
        m5.metric('Analisados pela IA',stats['ai_analyzed'])
        m6.metric('Revisados por pessoa',stats['human_reviewed'])
        a,b=st.columns(2)
        with a:
            st.markdown('**Artigos por base**')
            st.dataframe(pd.DataFrame([{'Base':k,'Artigos':v} for k,v in stats['sources'].items()]),
                         hide_index=True,use_container_width=True)
        with b:
            st.markdown('**Artigos por ano**')
            st.dataframe(pd.DataFrame([{'Ano':k,'Artigos':v} for k,v in stats['years'].items()]),
                         hide_index=True,use_container_width=True)
        st.divider()
        st.markdown('**2. Exportação bibliográfica RIS e CSV**')
        st.caption('Exporte a coleção inteira ou selecione manualmente os artigos desejados.')
        keep_duplicates=st.checkbox('Incluir artigos marcados como duplicatas',value=False,key=f'ris_dups_{did}')
        bibliographic=[r for r in rows if keep_duplicates or not r.get('duplicate_removed')]
        manual_selection=st.checkbox('Selecionar manualmente os artigos para exportação',
                                     value=False,key=f'export_manual_{did}')
        export_records=bibliographic
        if manual_selection:
            if bibliographic:
                page_size=st.select_slider('Artigos por página',options=[10,25,50,100],value=25,
                                            key=f'page_size_{did}')
                pages=max(1,(len(bibliographic)+page_size-1)//page_size)
                page=st.number_input('Página',min_value=1,max_value=pages,value=1,
                                     key=f'page_{did}')
                current_rows=bibliographic[(page-1)*page_size:page*page_size]
                st.caption(f'Exibindo {len(current_rows)} de {len(bibliographic)} artigos. Página {page}/{pages}.')
                # A seleção é guardada por identificador e preservada entre páginas.
                selected_pmids_key=f'export_selected_pmids_{did}'
                selected_pmids=st.session_state.setdefault(selected_pmids_key,set())
                current_ids={str(r['pmid']) for r in current_rows}
                # Descartar apenas IDs que não fazem mais parte da coleção.
                eligible_ids={str(r['pmid']) for r in bibliographic}
                selected_pmids.intersection_update(eligible_ids)
                table_key=f'export_table_{did}_{page}_{page_size}_{int(keep_duplicates)}'
                table=st.dataframe(pd.DataFrame(current_rows),hide_index=True,
                                   use_container_width=True,on_select='rerun',
                                   selection_mode='multi-row',key=table_key)
                page_chosen={str(current_rows[i]['pmid']) for i in table.selection.rows
                             if isinstance(i,int) and 0<=i<len(current_rows)}
                # Só atualizar a página visitada; escolhas feitas em outras páginas permanecem.
                selected_pmids.difference_update(current_ids-page_chosen)
                selected_pmids.update(page_chosen)
                st.caption(f'{len(selected_pmids)} artigo(s) selecionado(s) para exportação.')
                if st.button('Limpar seleção',key=f'clear_export_selection_{did}'):
                    selected_pmids.clear()
                    st.rerun()
                export_records=[r for r in bibliographic if str(r['pmid']) in selected_pmids]
            else:
                st.info('Nenhum artigo disponível para seleção.')
                export_records=[]
        st.caption(f'{len(export_records)} artigo(s) serão exportados.')
        x,y=st.columns(2)
        x.download_button('Baixar RIS',ris_bytes(export_records),
            file_name=f'colecao_{did}.ris',mime='application/x-research-info-systems',
            disabled=not export_records,use_container_width=True)
        y.download_button('Baixar CSV',csv_bytes(export_records),
            file_name=f'colecao_{did}.csv',mime='text/csv',
            disabled=not export_records,use_container_width=True)
        st.divider()
        st.markdown('**3. Salvar e restaurar coleção por arquivo**')
        st.caption('A aplicação principal já utiliza SQLite. Este backup JSON é uma cópia portátil '
                   'de uma coleção, incluindo revisões, critérios, marcações e extrações salvas. '
                   'Não inclui os PDFs originais nem senhas.')
        st.download_button('Baixar backup desta coleção (JSON)',
            build_backup(current_dataset,rows,get_extractions(did)),
            file_name=f'backup_colecao_{did}.json',mime='application/json',
            use_container_width=True)
        restore_upload=st.file_uploader('Restaurar coleção a partir de backup JSON',type=['json'],
                                        key=f'restore_upload_{did}')
        if restore_upload is not None:
            try:
                restored_meta,restored_rows,restored_ext=read_backup(restore_upload.getvalue())
                st.info(f"Coleção no arquivo: {restored_meta.get('name','sem nome')} | "
                        f'{len(restored_rows)} artigos | {len(restored_ext)} extrações')
                restore_confirm=st.checkbox('Confirmo a criação de uma nova coleção a partir deste backup',
                                             key=f'restore_confirm_{did}')
                if st.button('Restaurar como nova coleção',disabled=not restore_confirm,
                             key=f'restore_button_{did}'):
                    new_did=restore_collection(restored_meta,restored_rows,restored_ext)
                    st.success(f'Coleção restaurada com sucesso (ID {new_did}). '
                               'Selecione-a na lista de coleções.')
                    st.rerun()
            except Exception as exc:
                st.error(f'Backup não pôde ser restaurado: {exc}')

