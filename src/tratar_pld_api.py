"""Raw (API) -> tratada. Lê raw_ccee_pld_api, valida e grava
pld_horario_api_tratado; o que falhar vai para pld_api_quarentena."""
import json

import pandas as pd
from sqlalchemy import text

from src.database import conectar_banco

SUBMERCADOS_VALIDOS = {"NORTE", "NORDESTE", "SUL", "SUDESTE"}


def criar_tabelas(conexao):
    conexao.execute(text("""
        CREATE TABLE IF NOT EXISTS pld_horario_api_tratado (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            mes_referencia INT NOT NULL,
            submercado VARCHAR(20) NOT NULL,
            periodo_comercializacao INT NOT NULL,
            dia INT NOT NULL,
            hora INT NOT NULL,
            pld_hora DECIMAL(12,2) NOT NULL,
            data_hora DATETIME NOT NULL,
            arquivo_origem VARCHAR(50) NOT NULL,
            UNIQUE KEY uq_pld_hora (data_hora, submercado)
        )
    """))
    conexao.execute(text("""
        CREATE TABLE IF NOT EXISTS pld_api_quarentena (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            id_raw BIGINT UNSIGNED NOT NULL,
            motivo VARCHAR(100) NOT NULL,
            payload LONGTEXT NOT NULL
        )
    """))


def tratar(df):
    """Devolve (validos, rejeitados[com coluna motivo]). Função reutilizável."""
    df = df.copy()
    df.columns = [c.upper() for c in df.columns]
    df["SUBMERCADO"] = df["SUBMERCADO"].astype(str).str.strip().str.upper()
    for col in ["MES_REFERENCIA", "PERIODO_COMERCIALIZACAO", "DIA", "HORA"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["PLD_HORA"] = pd.to_numeric(df["PLD_HORA"], errors="coerce")

    base = pd.to_datetime(
        df["MES_REFERENCIA"].astype("Int64").astype(str)
        + df["DIA"].astype("Int64").astype(str).str.zfill(2),
        format="%Y%m%d", errors="coerce",
    )
    df["DATA_HORA"] = base + pd.to_timedelta(df["HORA"], unit="h")

    df["motivo"] = None
    df.loc[df["PLD_HORA"].isna(), "motivo"] = "pld_nulo_ou_invalido"
    df.loc[df["DATA_HORA"].isna(), "motivo"] = "data_invalida"
    df.loc[~df["SUBMERCADO"].isin(SUBMERCADOS_VALIDOS), "motivo"] = "submercado_invalido"
    df.loc[~df["HORA"].between(0, 23), "motivo"] = "hora_fora_da_faixa"
    df.loc[df["PLD_HORA"] < 0, "motivo"] = "pld_negativo"

    dup = df["motivo"].isna() & df.duplicated(["DATA_HORA", "SUBMERCADO"], keep="first")
    df.loc[dup, "motivo"] = "duplicado"

    return df[df["motivo"].isna()], df[df["motivo"].notna()]


def main():
    engine = conectar_banco()
    try:
        with engine.begin() as c:
            criar_tabelas(c)
            linhas = c.execute(text(
                "SELECT id, resource_id, payload FROM raw_ccee_pld_api ORDER BY id"
            )).fetchall()

        if not linhas:
            print("Raw vazio. Rode antes: python -m src.extrair_pld_api")
            return

        df = pd.DataFrame([json.loads(l.payload) for l in linhas])
        df["id_raw"] = [l.id for l in linhas]
        df["resource_id"] = [l.resource_id for l in linhas]

        validos, rejeitados = tratar(df)
        print(f"Raw: {len(df)} | válidos: {len(validos)} | quarentena: {len(rejeitados)}")

        with engine.begin() as c:
            c.execute(text("DELETE FROM pld_api_quarentena"))
            c.execute(text("DELETE FROM pld_horario_api_tratado"))

            if len(rejeitados):
                c.execute(
                    text("INSERT INTO pld_api_quarentena (id_raw, motivo, payload) "
                         "VALUES (:i, :m, :p)"),
                    [{"i": int(r.id_raw), "m": r.motivo,
                      "p": json.dumps({k: (None if pd.isna(v) else str(v))
                                       for k, v in r._asdict().items()
                                       if k not in ("Index",)}, ensure_ascii=False)}
                     for r in rejeitados.itertuples()],
                )

            sql = text("""
                INSERT INTO pld_horario_api_tratado
                (mes_referencia, submercado, periodo_comercializacao, dia, hora,
                 pld_hora, data_hora, arquivo_origem)
                VALUES (:m, :s, :p, :d, :h, :pld, :dh, :o)
            """)
            for i in range(0, len(validos), 2000):
                lote = validos.iloc[i:i + 2000]
                c.execute(sql, [{
                    "m": int(r.MES_REFERENCIA), "s": r.SUBMERCADO,
                    "p": int(r.PERIODO_COMERCIALIZACAO), "d": int(r.DIA),
                    "h": int(r.HORA), "pld": round(float(r.PLD_HORA), 2),
                    "dh": r.DATA_HORA.to_pydatetime(), "o": r.resource_id[:50],
                } for r in lote.itertuples()])

        print("Tratada carregada em pld_horario_api_tratado.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
