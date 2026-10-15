"""Contagens automáticas e auditáveis das decisões humanas para o PRISMA."""
from collections import Counter

def review_status_counts(rows):
    active = [r for r in rows if not r.get("duplicate_removed")]
    statuses = Counter((str(r.get("human_label") or "Pendente").strip().capitalize()) for r in active)
    result = {name: statuses.get(name, 0) for name in ("Incluir", "Excluir", "Incerto", "Pendente")}
    result["total_ativos"] = len(active)
    result["avaliados"] = result["Incluir"] + result["Excluir"] + result["Incerto"]
    result["aguardando_decisao"] = result["Incerto"] + result["Pendente"]
    return result
