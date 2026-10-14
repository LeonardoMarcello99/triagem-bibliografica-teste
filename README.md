# Triagem bibliográfica — demonstração web

Aplicação de teste para **2 a 10 pesquisadores** usando Streamlit Community Cloud. Não inclui Ollama, triagem por IA, revisão humana nem extração de PDFs.

## Publicar
1. Crie um repositório GitHub novo (preferencialmente privado) e envie `app.py`, `pubmed.py`, `sources.py`, `requirements.txt` e este README para a raiz.
2. Entre em https://share.streamlit.io e selecione **Create app** > repositório, branch e `app.py`.
3. Aguarde a instalação automática de dependências. Compartilhe o link somente com os participantes desejados.
4. Cada pessoa informa seu próprio e-mail NCBI na barra lateral, busca no PubMed ou importa arquivos RIS/NBIB/CSV/TSV.
5. Exporte os resultados em **Artigos e exportação** antes de fechar a sessão.

## Limitações e segurança
- **Sem login e sem persistência.** Dados ficam em `st.session_state` na memória do servidor e podem desaparecer após reinício, inatividade ou recarregamento. Não há garantia de armazenamento.
- As sessões do Streamlit são isoladas, mas não há autenticação. Um link público não equivale a controle de acesso. Para dados privados, use a configuração de acesso privado disponível na sua conta/implantação ou implemente login antes de publicar.
- Não envie PDFs licenciados, dados pessoais ou material confidencial nesta demonstração.
- Não há banco SQLite compartilhado; usuários não compartilham coleções.
- A importação substitui registros com identificadores iguais na mesma sessão.
- O PubMed é limitado a **2.000 registros por busca** nesta demonstração, para evitar sobrecarga da instância gratuita.
- A API PubMed exige e-mail válido e aplica limites de taxa; muitos usuários ao mesmo tempo podem causar lentidão.
- Embase/Cochrane apenas por arquivos exportados. Sem acesso às APIs dessas bases.
