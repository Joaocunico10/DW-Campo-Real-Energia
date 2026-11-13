
from sqlalchemy import text

from src.database import conectar_banco


def tratar_pld():
    engine = conectar_banco()

    with engine.begin() as conexao:

        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS pld_dw_tratado (
                id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                id_origem BIGINT NOT NULL,
                mes_referencia INT NOT NULL,
                submercado VARCHAR(20) NOT NULL,
                periodo_comercializacao INT NOT NULL,
                dia INT NOT NULL,
                hora INT NOT NULL,
                pld_hora DECIMAL(12,2) NOT NULL,
                data_hora DATETIME NOT NULL,
                arquivo_origem VARCHAR(50),
                UNIQUE KEY uq_pld_dw (data_hora, submercado)
            )
        """))

        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS pld_dw_quarentena (
                id_origem BIGINT PRIMARY KEY,
                submercado VARCHAR(20),
                data_hora DATETIME,
                pld_hora DECIMAL(12,2),
                motivo VARCHAR(255) NOT NULL
            )
        """))

        conexao.execute(text("DELETE FROM pld_dw_tratado"))
        conexao.execute(text("DELETE FROM pld_dw_quarentena"))

        # Registros com campos obrigatórios ausentes vão para quarentena.
        conexao.execute(text("""
            INSERT INTO pld_dw_quarentena
                (id_origem, submercado, data_hora, pld_hora, motivo)
            SELECT
                id,
                submercado,
                data_hora,
                pld_hora,
                CASE
                    WHEN submercado IS NULL THEN 'Submercado ausente'
                    WHEN data_hora IS NULL THEN 'Data e hora ausentes'
                    WHEN pld_hora IS NULL THEN 'Valor do PLD ausente'
                    ELSE 'Campo obrigatório inválido'
                END
            FROM pld_horario_api_tratado
            WHERE submercado IS NULL
               OR data_hora IS NULL
               OR pld_hora IS NULL
        """))

        # Registros válidos são copiados sem alterar o valor do PLD.
        conexao.execute(text("""
            INSERT INTO pld_dw_tratado (
                id_origem,
                mes_referencia,
                submercado,
                periodo_comercializacao,
                dia,
                hora,
                pld_hora,
                data_hora,
                arquivo_origem
            )
            SELECT
                id,
                mes_referencia,
                submercado,
                periodo_comercializacao,
                dia,
                hora,
                pld_hora,
                data_hora,
                arquivo_origem
            FROM pld_horario_api_tratado
            WHERE submercado IS NOT NULL
              AND data_hora IS NOT NULL
              AND pld_hora IS NOT NULL
        """))

        tratados = conexao.execute(
            text("SELECT COUNT(*) FROM pld_dw_tratado")
        ).scalar()

        quarentena = conexao.execute(
            text("SELECT COUNT(*) FROM pld_dw_quarentena")
        ).scalar()

        print("\nTRATAMENTO DO PLD FINALIZADO")
        print(f"Registros tratados: {tratados}")
        print(f"Registros em quarentena: {quarentena}")


if __name__ == "__main__":
    tratar_pld()
