def aplicar_condicao(filtro_sql, condicao):
    if filtro_sql:
        return filtro_sql + " AND " + condicao
    else:
        return "WHERE " + condicao