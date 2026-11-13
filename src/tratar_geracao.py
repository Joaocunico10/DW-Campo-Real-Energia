
from sqlalchemy import text

from src.database import conectar_banco


def tratar_geracao():
    engine = conectar_banco()

    with engine.begin() as conexao:

        # Tabela de dados tratados
        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS geracao_tratada (
                id_medicao BIGINT PRIMARY KEY,
                id_usina INT NOT NULL,
                data_hora DATETIME NOT NULL,
                energia_mwh DECIMAL(12,3) NOT NULL,
                disponibilidade_mw DECIMAL(8,2),
                origem VARCHAR(20),
                recebido_em DATETIME,
                correcao_aplicada VARCHAR(255),
                alerta_qualidade VARCHAR(255)
            )
        """))

        # Tabela de registros em quarentena
        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS geracao_quarentena (
                id_medicao BIGINT PRIMARY KEY,
                id_usina INT,
                data_hora DATETIME,
                energia_mwh DECIMAL(12,3),
                disponibilidade_mw DECIMAL(8,2),
                origem VARCHAR(20),
                recebido_em DATETIME,
                motivo_quarentena VARCHAR(255) NOT NULL
            )
        """))

        # Limpa somente nossas tabelas de tratamento.
        # As tabelas originais permanecem intactas.
        conexao.execute(text("DELETE FROM geracao_tratada"))
        conexao.execute(text("DELETE FROM geracao_quarentena"))

        conexao.execute(text("""
            DROP TEMPORARY TABLE IF EXISTS tmp_geracao_analise
        """))

        # Identifica duplicidades e problemas
        conexao.execute(text("""
            CREATE TEMPORARY TABLE tmp_geracao_analise AS
            SELECT
                m.*,

                ROW_NUMBER() OVER (
                    PARTITION BY m.id_usina, m.data_hora
                    ORDER BY m.recebido_em DESC, m.id_medicao DESC
                ) AS numero_duplicidade,

                CASE
                    WHEN m.id_usina IS NULL
                        THEN 'Identificador da usina nulo'

                    WHEN m.energia_mwh IS NULL
                        THEN 'Energia não informada'

                    WHEN m.energia_mwh < 0
                        THEN 'Energia negativa'

                    WHEN m.data_hora < '2025-01-01'
                      OR m.data_hora >= '2027-01-01'
                        THEN 'Data fora do período do projeto'

                    WHEN u.id_usina IS NULL
                        THEN 'Usina não cadastrada'

                    WHEN ROW_NUMBER() OVER (
                        PARTITION BY m.id_usina, m.data_hora
                        ORDER BY m.recebido_em DESC, m.id_medicao DESC
                    ) > 1
                        THEN 'Registro duplicado'

                    ELSE NULL
                END AS motivo_quarentena

            FROM medicao_geracao m
            LEFT JOIN usina u
                ON m.id_usina = u.id_usina
        """))

        # Envia problemas para quarentena
        conexao.execute(text("""
            INSERT INTO geracao_quarentena (
                id_medicao,
                id_usina,
                data_hora,
                energia_mwh,
                disponibilidade_mw,
                origem,
                recebido_em,
                motivo_quarentena
            )
            SELECT
                id_medicao,
                id_usina,
                data_hora,
                energia_mwh,
                disponibilidade_mw,
                origem,
                recebido_em,
                motivo_quarentena
            FROM tmp_geracao_analise
            WHERE motivo_quarentena IS NOT NULL
        """))

        # Insere somente registros válidos na camada tratada
        # com correções de unidade identificadas na análise.
        conexao.execute(text("""
            INSERT INTO geracao_tratada (
                id_medicao,
                id_usina,
                data_hora,
                energia_mwh,
                disponibilidade_mw,
                origem,
                recebido_em,
                correcao_aplicada,
                alerta_qualidade
            )
            SELECT
                m.id_medicao,
                m.id_usina,
                m.data_hora,

                CASE
                    WHEN m.id_usina = 1
                     AND DATE(m.data_hora) = '2025-05-10'
                     AND m.energia_mwh BETWEEN 28000 AND 35000
                        THEN m.energia_mwh / 1000

                    WHEN m.id_usina = 7
                     AND m.data_hora = '2025-04-22 14:00:00'
                     AND m.energia_mwh = 1228.760
                        THEN m.energia_mwh / 10

                    ELSE m.energia_mwh
                END,

                m.disponibilidade_mw,
                m.origem,
                m.recebido_em,

                CASE
                    WHEN m.id_usina = 1
                     AND DATE(m.data_hora) = '2025-05-10'
                     AND m.energia_mwh BETWEEN 28000 AND 35000
                        THEN 'Conversão de kWh para MWh (divisão por 1000)'

                    WHEN m.id_usina = 7
                     AND m.data_hora = '2025-04-22 14:00:00'
                     AND m.energia_mwh = 1228.760
                        THEN 'Correção de valor multiplicado por 10'

                    ELSE NULL
                END,

                CASE
                    WHEN m.recebido_em < m.data_hora
                        THEN 'Recebimento anterior à medição'

                    WHEN m.disponibilidade_mw IS NULL
                        THEN 'Disponibilidade não informada'

                    WHEN u.data_inicio_operacao > DATE(m.data_hora)
                        THEN 'Medição anterior ao início de operação cadastrado'

                    ELSE NULL
                END

            FROM tmp_geracao_analise m
            INNER JOIN usina u
                ON m.id_usina = u.id_usina
            WHERE m.motivo_quarentena IS NULL
        """))

        # Resultado
        tratados = conexao.execute(text("""
            SELECT COUNT(*) FROM geracao_tratada
        """)).scalar()

        quarentena = conexao.execute(text("""
            SELECT COUNT(*) FROM geracao_quarentena
        """)).scalar()

        print("\nTRATAMENTO FINALIZADO")
        print(f"Registros tratados: {tratados}")
        print(f"Registros em quarentena: {quarentena}")


if __name__ == "__main__":
    tratar_geracao()
