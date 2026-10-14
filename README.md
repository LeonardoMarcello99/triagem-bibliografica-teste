# Triagem Bibliográfica

Aplicação web desenvolvida para facilitar as primeiras etapas de uma pesquisa bibliográfica: **buscar referências científicas, importar resultados de bases de dados, consultar informações dos artigos e exportar os registros para análise posterior**.

O projeto está em fase de validação com um pequeno grupo de pesquisadores. Esta versão é uma demonstração funcional e não exige instalação de software por parte de quem acessa o site.

## O que é possível fazer

- **Buscar no PubMed:** construir consultas com termos, campos de busca e operadores booleanos `AND`, `OR` e `NOT`.
- **Reutilizar pesquisas:** consultar o histórico da sessão e combinar buscas anteriores usando o menu de ações.
- **Importar referências:** carregar arquivos `.ris`, `.nbib`, `.csv` e `.tsv`, incluindo exportações de bases como PubMed, Embase e Cochrane.
- **Explorar os resultados:** visualizar uma tabela de artigos e selecionar registros para consultar título, resumo, periódico, ano, DOI e links disponíveis, incluindo acesso direto ao PubMed quando identificado.
- **Exportar dados:** escolher colunas e baixar os resultados em formato Excel (`.xlsx`).

As referências obtidas por busca e importação podem ser reunidas durante a mesma sessão. Identificadores repetidos podem resultar na substituição de registros anteriores.

## Para quem é indicado

Pesquisadores, estudantes e profissionais que realizam levantamentos de literatura científica e desejam reunir referências de diferentes fontes em um único ambiente de consulta e exportação.

## Como utilizar

1. Acesse o endereço da aplicação disponibilizado pelo responsável pelo teste.
2. Para pesquisar no PubMed, informe um e-mail de contato na barra lateral e monte sua consulta em **Busca PubMed**.
3. Para carregar referências já exportadas de outras bases, utilize **Importar arquivos**.
4. Acesse **Artigos e exportação** para consultar os registros e baixar uma planilha Excel.

> **Importante:** esta versão utiliza armazenamento temporário por sessão. Exporte os resultados antes de sair; eles podem ser perdidos ao atualizar a página, encerrar a sessão ou reiniciar o servidor.

## Escopo desta versão

Esta demonstração contempla **busca, importação, visualização e exportação de referências**. Não inclui triagem automatizada com inteligência artificial, revisão de elegibilidade, extração de dados de PDFs, cadastro de usuários ou salvamento permanente de coleções.

A consulta ao PubMed utiliza os serviços do NCBI e está limitada a **2.000 registros por busca** nesta versão de testes. As demais bases são utilizadas por meio de arquivos exportados, sem conexão direta com suas APIs.

## Privacidade e limitações

- Não existe autenticação própria nesta versão. Caso a aplicação seja publicada com acesso público, qualquer pessoa com o endereço poderá acessá-la.
- Os dados são mantidos temporariamente na sessão do Streamlit, sem um banco de dados persistente. Não há garantia de recuperação após encerramento ou interrupção.
- Não utilize a demonstração para armazenar dados pessoais sensíveis, documentos confidenciais ou materiais cujo compartilhamento não seja autorizado.
- As informações bibliográficas dependem da qualidade dos registros fornecidos pelas bases e arquivos de origem. Recomenda-se conferir os dados antes de utilizá-los em publicações.
- O desempenho e a disponibilidade podem variar conforme a hospedagem e os limites de acesso à API PubMed.

## Tecnologias

- **Python** — linguagem principal.
- **Streamlit** — interface web.
- **NCBI Entrez / Biopython** — consulta ao PubMed.
- **Pandas e OpenPyXL** — organização e exportação de dados.

## Executar localmente

Requisitos: Python 3.10 ou superior.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

A aplicação será aberta no navegador. Para publicar na web, é possível utilizar o [Streamlit Community Cloud](https://share.streamlit.io) conectando este repositório ao serviço e indicando `app.py` como arquivo principal.

## Situação do projeto

**Protótipo em validação.** O objetivo desta etapa é coletar opiniões sobre usabilidade, organização da busca, importação de referências e exportação. Funcionalidades adicionais poderão ser incorporadas em versões futuras conforme as necessidades identificadas.

---

*Este projeto é independente e não possui afiliação oficial com o PubMed ou o NCBI.*
