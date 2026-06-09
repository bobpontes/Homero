from datetime import date
import calendar

def adicionar_meses(data_base, meses):
    dia_original = data_base.day

    mes = data_base.month -1 + meses
    ano = data_base.year + mes // 12
    mes = mes % 12 + 1
    
    ultimo_dia = calendar.monthrange(ano, mes)[1]

    # mantém o mesmo dia sempre que possível
    dia = dia_original if dia_original <= ultimo_dia else ultimo_dia
    return date(ano, mes, dia)