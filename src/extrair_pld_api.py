"""Etapa 1A: extrai o PLD horário da CCEE pela API CKAN e grava a camada raw.

Cada registro é guardado exatamente como chegou (JSON), com origem e data/hora
da extração. Cada execução é registrada em log_extracao.
Reexecutar não duplica nem rebaixa tudo: retoma de onde parou.
"""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from src import ccee_api
from src.database import conectar_banco

ANOS = [2025, 2026]
FONTE = "CCEE PLD_HORARIO (API CKAN)"
FONTE_FALLBACK = "CCEE PLD_HORARIO (CSV - fallback autorizado)"
PASTA_CSV = Path(__file__).resolve().parent.parent / "data" / "entrada"


def criar_tabelas(conexao):
    conexao.execute(text("""
        CREATE TABLE IF NOT EXISTS raw_ccee_pld_api (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            resource_id VARCHAR(64) NOT NULL,
            ano SMALLINT NOT NULL,
            record_id BIGINT NOT NULL,
            pagina_offset INT NOT NULL,
            payload LONGTEXT NOT NULL,
            origem VARCHAR(255) NOT NULL,
            extraido_em DATETIME(6) NOT NULL,
            id_execucao BIGINT UNSIGNED NOT NULL,
            UNIQUE KEY uq_recurso_registro (resource_id, record_id)
        )
    """))
    conexao.execute(text("""
        CREATE TABLE IF NOT EXISTS log_extracao (
            id_execucao BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            fonte VARCHAR(100) NOT NULL,
            recurso VARCHAR(100) NULL,
            inicio DATETIME(6) NOT NULL,
            fim DATETIME(6) NULL,
            linhas_lidas BIGINT NOT NULL DEFAULT 0,
            linhas_gravadas BIGINT NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL,
            erro TEXT NULL
        )
    """))


def agora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def abrir_log(engine, recurso, fonte=None):
    with engine.begin() as c:
        r = c.execute(
            text("""INSERT INTO log_extracao (fonte, recurso, inicio, status)
                    VALUES (:f, :r, :i, 'EXECUTANDO')"""),
            {"f": fonte or FONTE, "r": recurso, "i": agora()},
        )
        return r.lastrowid


def fechar_log(engine, id_execucao, lidas, gravadas, status, erro=None):
    with engine.begin() as c:
        c.execute(
            text("""UPDATE log_extracao
                    SET fim=:fim, linhas_lidas=:l, linhas_gravadas=:g,
                        status=:s, erro=:e
                    WHERE id_execucao=:id"""),
            {"fim": agora(), "l": lidas, "g": gravadas,
             "s": status, "e": erro, "id": id_execucao},
        )


def extrair_recurso(engine, ano, resource_id):
    id_exec = abrir_log(engine, f"{ano}:{resource_id}")
    lidas = gravadas = 0
    alertas = []

    try:
        # Retoma de onde parou (não rebaixa o que já está no banco)
        with engine.connect() as c:
            ja_gravadas = c.execute(
                text("SELECT COUNT(*) FROM raw_ccee_pld_api WHERE resource_id=:r"),
                {"r": resource_id},
            ).scalar()
        offset_inicial = (ja_gravadas // ccee_api.LIMITE_PAGINA) * ccee_api.LIMITE_PAGINA

        sql = text("""
            INSERT IGNORE INTO raw_ccee_pld_api
            (resource_id, ano, record_id, pagina_offset, payload,
             origem, extraido_em, id_execucao)
            VALUES (:resource_id, :ano, :record_id, :pagina_offset, :payload,
                    :origem, :extraido_em, :id_execucao)
        """)

        for offset, registros, total in ccee_api.paginar(resource_id, offset_inicial):
            if offset == offset_inicial:
                faltando, extras = ccee_api.colunas_diferentes(registros[0])
                if faltando or extras:
                    alertas.append(
                        f"Esquema mudou: faltando={sorted(faltando)} extras={sorted(extras)}"
                    )

            extraido_em = agora()
            lote = [{
                "resource_id": resource_id,
                "ano": ano,
                "record_id": int(r["_id"]),
                "pagina_offset": offset,
                "payload": json.dumps(r, ensure_ascii=False),
                "origem": f"{ccee_api.API_URL}/datastore_search?resource_id={resource_id}",
                "extraido_em": extraido_em,
                "id_execucao": id_exec,
            } for r in registros]

            with engine.begin() as c:
                gravadas += c.execute(sql, lote).rowcount
            lidas += len(registros)
            print(f"[{ano}] offset={offset} lidas={lidas}/{total}")

        if lidas == 0 and ja_gravadas == 0:
            fechar_log(engine, id_exec, 0, 0, "VAZIO", "API devolveu 0 registros")
            return False
        status = "SUCESSO_COM_ALERTA" if alertas else "SUCESSO"
        fechar_log(engine, id_exec, lidas, gravadas, status, "; ".join(alertas) or None)
        return True

    except Exception as erro:  # registra a falha e segue para o próximo ano
        fechar_log(engine, id_exec, lidas, gravadas, "ERRO", str(erro)[:2000])
        print(f"[{ano}] ERRO: {erro}")
        return False


def ler_csv_bruto(caminho):
    """Lê o CSV sem converter nada: todos os valores continuam texto."""
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def carregar_csv_fallback(engine, ano, motivo):
    """Plano B autorizado pela professora: CSV baixado do portal da CCEE.
    Grava na MESMA tabela raw da API, marcando a origem e o motivo."""
    caminho = PASTA_CSV / f"pld_{ano}.csv"
    id_exec = abrir_log(engine, f"{ano}:{caminho.name}", FONTE_FALLBACK)

    if not caminho.exists():
        fechar_log(engine, id_exec, 0, 0, "ERRO", f"Arquivo não encontrado: {caminho}")
        print(f"[{ano}] CSV não encontrado: {caminho}")
        return

    try:
        hash_arquivo = hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]
        registros = ler_csv_bruto(caminho)
        extraido_em = agora()
        origem = f"CSV manual {caminho.name} sha256:{hash_arquivo} | {motivo}"

        sql = text("""
            INSERT IGNORE INTO raw_ccee_pld_api
            (resource_id, ano, record_id, pagina_offset, payload,
             origem, extraido_em, id_execucao)
            VALUES (:resource_id, :ano, :record_id, 0, :payload,
                    :origem, :extraido_em, :id_execucao)
        """)

        gravadas = 0
        for ini in range(0, len(registros), 5000):
            lote = [{
                "resource_id": caminho.name,
                "ano": ano,
                "record_id": ini + n,  # nº da linha de dados no arquivo
                "payload": json.dumps(r, ensure_ascii=False),
                "origem": origem,
                "extraido_em": extraido_em,
                "id_execucao": id_exec,
            } for n, r in enumerate(registros[ini:ini + 5000], start=1)]
            with engine.begin() as c:
                gravadas += c.execute(sql, lote).rowcount

        faltando, extras = ccee_api.colunas_diferentes(registros[0]) if registros else (set(), set())
        alerta = f"Esquema: faltando={sorted(faltando)} extras={sorted(extras)}" if (faltando or extras) else None
        fechar_log(engine, id_exec, len(registros), gravadas,
                   "SUCESSO_FALLBACK", alerta)
        print(f"[{ano}] fallback CSV: lidas={len(registros)} gravadas={gravadas}")
    except Exception as erro:
        fechar_log(engine, id_exec, 0, 0, "ERRO", str(erro)[:2000])
        print(f"[{ano}] ERRO no fallback: {erro}")


def main():
    engine = conectar_banco()
    try:
        with engine.begin() as c:
            criar_tabelas(c)

        # 1) tenta a API; se a CCEE bloquear (ex.: 403), registra e cai no plano B
        recursos, motivo = {}, None
        try:
            recursos = ccee_api.descobrir_recursos(ANOS)
        except Exception as erro:
            motivo = f"API indisponível: {str(erro)[:200]}"
            id_exec = abrir_log(engine, "package_show")
            fechar_log(engine, id_exec, 0, 0, "ERRO", str(erro)[:2000])
            print(f"API bloqueada/indisponível: {erro}")

        for ano in ANOS:
            ok = False
            if ano in recursos:
                ok = extrair_recurso(engine, ano, recursos[ano])
            elif motivo is None:
                motivo = f"resource_id de {ano} não encontrado na API"
            if not ok:
                carregar_csv_fallback(
                    engine, ano,
                    motivo or f"API sem dados para {ano}; fallback autorizado pela professora",
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
