
from pathlib import Path
from decimal import Decimal
import pandas as pd

from sqlalchemy import text
from src.database import conectar_banco


PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO = PASTA_PROJETO / "data" / "tratada" / "pld_horario_2025_2026.csv"


def criar_tabela(conexao):
    sql = """
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
    """
    conexao.execute(text(sql))


def main():
    if not ARQUIVO.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {ARQUIVO}")

    dados = pd.read_csv(ARQUIVO)

    engine = conectar_banco()

    try:
        with engine.begin() as conexao:
            criar_tabela(conexao)

            sql = text("""
                INSERT IGNORE INTO pld_horario_api_tratado (
                    mes_referencia,
                    submercado,
                    periodo_comercializacao,
                    dia,
                    hora,
                    pld_hora,
                    data_hora,
                    arquivo_origem
                )
                VALUES (
                    :mes_referencia,
                    :submercado,
                    :periodo_comercializacao,
                    :dia,
                    :hora,
                    :pld_hora,
                    :data_hora,
                    :arquivo_origem
                )
            """)

            total_inserido = 0

            for inicio in range(0, len(dados), 1000):
                lote = dados.iloc[inicio:inicio + 1000]
                registros = []

                for linha in lote.to_dict("records"):
                    registros.append({
                        "mes_referencia": int(linha["MES_REFERENCIA"]),
                        "submercado": linha["SUBMERCADO"],
                        "periodo_comercializacao": int(
                            linha["PERIODO_COMERCIALIZACAO"]
                        ),
                        "dia": int(linha["DIA"]),
                        "hora": int(linha["HORA"]),
                        "pld_hora": Decimal(str(linha["PLD_HORA"])),
                        "data_hora": pd.to_datetime(
                            linha["DATA_HORA"]
                        ).to_pydatetime(),
                        "arquivo_origem": (
                            "pld_2025.csv"
                            if int(linha["MES_REFERENCIA"]) < 202600
                            else "pld_2026.csv"
                        )
                    })

                resultado = conexao.execute(sql, registros)
                total_inserido += resultado.rowcount

            total_banco = conexao.execute(
                text("SELECT COUNT(*) FROM pld_horario_api_tratado")
            ).scalar()

            print("\nCARGA TRATADA CONCLUÍDA!")
            print(f"Novos registros inseridos: {total_inserido}")
            print(f"Total na tabela: {total_banco}")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
