"""Cliente HTTP do portal de dados abertos da CCEE (CKAN).

Sem dependência de banco: só HTTP, paginação e tratamento de falhas.
"""
import os
import re
import time

import requests

API_URL = os.getenv("CCEE_API_URL", "https://dadosabertos.ccee.org.br/api/3/action")
DATASET = os.getenv("CCEE_DATASET", "pld_horario")
TIMEOUT = int(os.getenv("CCEE_TIMEOUT", 60))
TENTATIVAS = int(os.getenv("CCEE_TENTATIVAS", 5))
PAUSA_ENTRE_PAGINAS = float(os.getenv("CCEE_PAUSA", 0.5))
LIMITE_PAGINA = int(os.getenv("CCEE_LIMITE_PAGINA", 5000))

# Colunas esperadas no datastore (para detectar mudança de esquema)
COLUNAS_ESPERADAS = {
    "MES_REFERENCIA", "SUBMERCADO", "PERIODO_COMERCIALIZACAO",
    "DIA", "HORA", "PLD_HORA",
}


class ErroAPI(Exception):
    pass


def _get_json(acao, params):
    """GET com retry exponencial: timeout, conexão, 5xx, 429 e JSON inválido."""
    url = f"{API_URL}/{acao}"
    ultimo_erro = None

    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)

            if resp.status_code == 429:  # limite de requisições
                espera = int(resp.headers.get("Retry-After", 2 ** tentativa))
                ultimo_erro = f"HTTP 429 (aguardando {espera}s)"
                time.sleep(espera)
                continue

            if resp.status_code >= 500:
                ultimo_erro = f"HTTP {resp.status_code}"
                time.sleep(2 ** tentativa)
                continue

            resp.raise_for_status()  # 4xx (exceto 429) não adianta repetir

            corpo = resp.json()
            if not corpo.get("success", False):
                raise ErroAPI(f"API respondeu success=false: {corpo.get('error')}")
            return corpo["result"]

        except (requests.Timeout, requests.ConnectionError) as e:
            ultimo_erro = f"{type(e).__name__}: {e}"
            time.sleep(2 ** tentativa)
        except ValueError as e:  # JSON inválido / resposta vazia
            ultimo_erro = f"Resposta não é JSON válido: {e}"
            time.sleep(2 ** tentativa)

    raise ErroAPI(f"Falha após {TENTATIVAS} tentativas em {acao}: {ultimo_erro}")


def descobrir_recursos(anos):
    """Lê os metadados do dataset e devolve {ano: resource_id}.

    Permite sobrescrever via .env: CCEE_RESOURCE_PLD_2025=<id>
    """
    encontrados = {}

    for ano in anos:
        manual = os.getenv(f"CCEE_RESOURCE_PLD_{ano}")
        if manual:
            encontrados[ano] = manual

    faltando = [a for a in anos if a not in encontrados]
    if faltando:
        pacote = _get_json("package_show", {"id": DATASET})
        for rec in pacote.get("resources", []):
            texto = f"{rec.get('name', '')} {rec.get('url', '')}"
            achado = re.search(r"(20\d{2})", texto)
            if achado and int(achado.group(1)) in faltando:
                encontrados[int(achado.group(1))] = rec["id"]

    return encontrados


def buscar_pagina(resource_id, offset, limite=LIMITE_PAGINA):
    result = _get_json(
        "datastore_search",
        {"resource_id": resource_id, "limit": limite, "offset": offset},
    )
    return result.get("records", []), result.get("total")


def paginar(resource_id, offset_inicial=0):
    """Gera (offset, registros, total). Para quando a página vem vazia
    ou quando o offset alcança o total informado pela API."""
    offset = offset_inicial
    while True:
        registros, total = buscar_pagina(resource_id, offset)
        if not registros:
            return
        yield offset, registros, total
        offset += len(registros)
        if total is not None and offset >= total:
            return
        time.sleep(PAUSA_ENTRE_PAGINAS)


def colunas_diferentes(registro):
    """Devolve (faltando, extras) comparando com o esquema esperado."""
    chaves = {k.upper() for k in registro if k != "_id"}
    return COLUNAS_ESPERADAS - chaves, chaves - COLUNAS_ESPERADAS
