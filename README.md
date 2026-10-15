# LitScope — versão Web / GitHub

Aplicação Streamlit de apoio à pesquisa bibliográfica, baseada na versão principal **LitScope v35**. Mantém o mesmo layout, identidade visual e organização das oito guias.

## Recursos disponíveis

- **Busca e coleções:** consultas PubMed, histórico de pesquisas, importação RIS, NBIB, CSV e TSV e gerenciamento de coleções.
- **Duplicatas:** detecção e marcação reversível de registros repetidos.
- **Revisão/Filtro:** busca por palavras, filtros e classificação humana (Incluir, Excluir, Incerto e Pendente).
- **Exportação:** planilhas Excel e seleção de colunas.
- **Fluxograma PRISMA:** contagens automáticas da revisão, campos manuais para etapas posteriores, exportação SVG e CSV.
- **Backup e restauração de dados:** estatísticas, exportação RIS/CSV com seleção manual de artigos, backup JSON e restauração de coleções.
- **Triagem e Extração de dados:** exibem **Em desenvolvimento**. Não fazem chamadas de IA.

## Dados e privacidade

Esta versão é destinada a **testes temporários com poucas pessoas**, sem cadastro ou autenticação. Cada sessão recebe um **banco SQLite separado**, evitando acesso direto às coleções de outros visitantes. Não há persistência garantida: dados podem desaparecer após reinício, limpeza da hospedagem ou término da sessão. **Exporte RIS/CSV/Excel ou faça backup JSON antes de sair.** A restauração é feita na guia Backup e restauração de dados.

A separação por sessão não substitui autenticação, autorização, criptografia de dados em repouso nem uma arquitetura multiusuário para produção. Não use dados sensíveis ou confidenciais. Os resultados do PubMed dependem dos serviços NCBI.

## Limitações

As funcionalidades de IA foram intencionalmente desabilitadas. Os recursos de revisão manual, duplicatas, PRISMA, busca e exportação permanecem disponíveis. A importação de Embase e Cochrane é por arquivo; não há consulta direta às APIs dessas bases.

## Testes

```bash
python -m unittest -v test_web.py
```

O LitScope é um projeto independente, sem afiliação oficial ao PubMed ou NCBI.
