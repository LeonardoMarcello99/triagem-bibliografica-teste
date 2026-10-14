import os, time
from Bio import Entrez

def _text(element):
    return "".join(str(x) for x in element) if element is not None else ""

def search_pubmed(query, limit=None, email=""):
    if not email or "@" not in email:
        raise ValueError("Informe um e-mail válido para identificar as consultas à NCBI.")
    Entrez.email = email
    Entrez.tool = "LocalSystematicReviewScreener"
    if os.getenv("NCBI_API_KEY"):
        Entrez.api_key = os.environ["NCBI_API_KEY"]
    with Entrez.esearch(db="pubmed", term=query, retmax=0, usehistory="y") as h:
        data = Entrez.read(h)
    count = int(data["Count"])
    total = count if limit is None else min(count, int(limit))
    if total == 0:
        return [], count
    webenv = data["WebEnv"]
    query_key = data["QueryKey"]
    result = []
    # A busca usa o histórico da NCBI, evitando o limite de 10 mil PMIDs por esearch.
    for start in range(0, total, 100):
        batch_size = min(100, total - start)
        with Entrez.efetch(db="pubmed", rettype="xml", retmode="xml",
                           retstart=start, retmax=batch_size,
                           webenv=webenv, query_key=query_key) as h:
            records = Entrez.read(h)
        for entry in records.get("PubmedArticle", []):
            citation = entry["MedlineCitation"]
            article = citation["Article"]
            pmid = str(citation["PMID"])
            abstract = article.get("Abstract", {}).get("AbstractText", [])
            abstract_text = " ".join(
                (str(getattr(part, "attributes", {}).get("Label", "")) + ": " if getattr(part, "attributes", {}).get("Label") else "")
                + _text(part) for part in abstract
            ).strip()
            doi = ""
            for aid in entry.get("PubmedData", {}).get("ArticleIdList", []):
                if aid.attributes.get("IdType") == "doi":
                    doi = str(aid)
            pubdate = article.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
            year = str(pubdate.get("Year", pubdate.get("MedlineDate", "")))
            result.append(dict(
                pmid=pmid, title=_text(article.get("ArticleTitle", "")),
                abstract=abstract_text, year=year,
                journal=str(article.get("Journal", {}).get("Title", "")),
                doi=doi, url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            ))
        time.sleep(0.4 if not os.getenv("NCBI_API_KEY") else 0.12)
    return result, count


def count_pubmed(query, email):
    """Obtém apenas a contagem de resultados, sem importar artigos."""
    if not email or "@" not in email:
        raise ValueError("Informe um e-mail válido para consultar o PubMed.")
    Entrez.email = email
    Entrez.tool = "LocalSystematicReviewScreener"
    if os.getenv("NCBI_API_KEY"):
        Entrez.api_key = os.environ["NCBI_API_KEY"]
    with Entrez.esearch(db="pubmed", term=query, retmax=0) as handle:
        return int(Entrez.read(handle)["Count"])
