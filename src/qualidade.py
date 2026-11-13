
from sqlalchemy import text

from src.database import conectar_banco


def criar_tabela_qualidade():
    engine = conectar_banco()

    with engine.begin() as conexao:
        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS dw_qualidade_metricas (
                id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                tabela_analisada VARCHAR(100) NOT NULL,
                regra VARCHAR(100) NOT NULL,
                dimensao VARCHAR(50) NOT NULL,
                registros_avaliados BIGINT NOT NULL,
                registros_com_falha BIGINT NOT NULL,
                percentual_falha DECIMAL(8,4) NOT NULL,
                executado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))

    print("Tabela dw_qualidade_metricas criada/verificada!")
    

def verificar_completude(conexao, tabela, coluna, regra):
    consulta = text(f"""
        SELECT
            COUNT(*) AS total,
            SUM(
                CASE
                    WHEN `{coluna}` IS NULL THEN 1
                    ELSE 0
                END
            ) AS falhas
        FROM `{tabela}`
    """)

    resultado = conexao.execute(consulta).mappings().one()

    total = resultado["total"]
    falhas = resultado["falhas"] or 0

    percentual = (falhas / total * 100) if total > 0 else 0

    conexao.execute(
        text("""
            INSERT INTO dw_qualidade_metricas (
                tabela_analisada,
                regra,
                dimensao,
                registros_avaliados,
                registros_com_falha,
                percentual_falha
            )
            VALUES (
                :tabela,
                :regra,
                'completude',
                :total,
                :falhas,
                :percentual
            )
        """),
        {
            "tabela": tabela,
            "regra": regra,
            "total": total,
            "falhas": falhas,
            "percentual": percentual
        }
    )

    print(
        f"{tabela}.{coluna}: "
        f"{falhas} falhas de {total} registros "
        f"({percentual:.2f}%)"
    )


def executar_analise_completude():
    engine = conectar_banco()

    verificacoes = [
        ("usina", "nome", "Nome da usina preenchido"),
        ("usina", "latitude", "Latitude preenchida"),
        ("usina", "longitude", "Longitude preenchida"),
        ("medicao_geracao", "energia_mwh", "Energia preenchida"),
        ("medicao_geracao", "id_usina", "Usina identificada"),
        ("medicao_geracao", "disponibilidade_mw", "Disponibilidade preenchida"),
        ("pld_horario_api_tratado", "pld_hora", "PLD preenchido"),
        ("clima_horario_api_tratado", "temperatura", "Temperatura preenchida"),
        ("clima_horario_api_tratado", "precipitacao", "Precipitação preenchida"),
        ("clima_horario_api_tratado", "velocidade_vento", "Vento preenchido"),
        ("clima_horario_api_tratado", "radiacao_solar", "Radiação solar preenchida"),
        ("medicao_geracao", "data_hora", "Data da medição preenchida"),
        ("medicao_geracao", "recebido_em", "Recebimento preenchido"),
        ("pld_horario_api_tratado", "data_hora", "Data do PLD preenchida"),
        ("clima_horario_api_tratado", "data_hora", "Data do clima preenchida"),
    ]

    with engine.begin() as conexao:
        for tabela, coluna, regra in verificacoes:
            verificar_completude(
                conexao,
                tabela,
                coluna,
                regra
            )

    print("\nAnálise de completude finalizada!")


def registrar_regra_sql(conexao, tabela, regra, dimensao, consulta):
    resultado = conexao.execute(text(consulta)).mappings().one()

    total = int(resultado["total"] or 0)
    falhas = int(resultado["falhas"] or 0)

    percentual = (falhas / total * 100) if total else 0

    conexao.execute(
        text("""
            INSERT INTO dw_qualidade_metricas (
                tabela_analisada,
                regra,
                dimensao,
                registros_avaliados,
                registros_com_falha,
                percentual_falha
            )
            VALUES (
                :tabela, :regra, :dimensao,
                :total, :falhas, :percentual
            )
        """),
        {
            "tabela": tabela,
            "regra": regra,
            "dimensao": dimensao,
            "total": total,
            "falhas": falhas,
            "percentual": percentual
        }
    )

    print(
        f"{tabela} | {regra}: "
        f"{falhas} falhas de {total} "
        f"({percentual:.2f}%)"
    )


def executar_analise_avancada():
    engine = conectar_banco()

    verificacoes = [
        (
            "medicao_geracao",
            "Energia negativa",
            "validade",
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN energia_mwh < 0 THEN 1 ELSE 0 END) AS falhas
            FROM medicao_geracao
            """
        ),
        (
            "medicao_geracao",
            "Referência de usina inexistente",
            "integridade referencial",
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE
                       WHEN m.id_usina IS NOT NULL
                        AND u.id_usina IS NULL THEN 1
                       ELSE 0
                   END) AS falhas
            FROM medicao_geracao m
            LEFT JOIN usina u ON m.id_usina = u.id_usina
            """
        ),
        (
            "medicao_geracao",
            "Recebimento anterior à medição",
            "consistência",
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE
                       WHEN recebido_em < data_hora THEN 1
                       ELSE 0
                   END) AS falhas
            FROM medicao_geracao
            """
        ),
        (
            "medicao_geracao",
            "Data fora do período do projeto",
            "validade",
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE
                       WHEN data_hora < '2025-01-01'
                         OR data_hora >= '2027-01-01' THEN 1
                       ELSE 0
                   END) AS falhas
            FROM medicao_geracao
            """
        ),
        (
            "medicao_geracao",
            "Duplicidade por usina e horário",
            "unicidade",
            """
            SELECT
                (SELECT COUNT(*) FROM medicao_geracao) AS total,
                (
                    SELECT COALESCE(SUM(quantidade - 1), 0)
                    FROM (
                        SELECT COUNT(*) AS quantidade
                        FROM medicao_geracao
                        GROUP BY id_usina, data_hora
                        HAVING COUNT(*) > 1
                    ) AS duplicados
                ) AS falhas
            """
        ),
        (
            "usina",
            "Início de operação futuro",
            "validade",
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE
                       WHEN data_inicio_operacao > '2026-11-13' THEN 1
                       ELSE 0
                   END) AS falhas
            FROM usina
            """
        ),
        (
            "clima_horario_api_tratado",
            "Precipitação negativa",
            "validade",
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN precipitacao < 0 THEN 1 ELSE 0 END) AS falhas
            FROM clima_horario_api_tratado
            """
        ),
        (
            "clima_horario_api_tratado",
            "Velocidade do vento negativa",
            "validade",
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN velocidade_vento < 0 THEN 1 ELSE 0 END) AS falhas
            FROM clima_horario_api_tratado
            """
        ),
        (
            "clima_horario_api_tratado",
            "Radiação solar negativa",
            "validade",
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN radiacao_solar < 0 THEN 1 ELSE 0 END) AS falhas
            FROM clima_horario_api_tratado
            """
        )
    ]

    with engine.begin() as conexao:
        for tabela, regra, dimensao, consulta in verificacoes:
            registrar_regra_sql(
                conexao,
                tabela,
                regra,
                dimensao,
                consulta
            )

    print("\nAnálise avançada finalizada!")


if __name__ == "__main__":
    criar_tabela_qualidade()
    executar_analise_completude()
    executar_analise_avancada()

