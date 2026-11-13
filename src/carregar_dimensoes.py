
from datetime import timedelta
from sqlalchemy import text

from src.database import conectar_banco


def carregar_dimensoes():
    engine = conectar_banco()
    
    DW = "dw_campo_real"
    ORIGEM = "campo_real_energia"

    dias = [
        "Segunda-feira", "Terça-feira", "Quarta-feira",
        "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"
    ]

    with engine.begin() as conexao:

        # ------------------------------------------------
        # 1. CORRIGIR O MEMBRO DESCONHECIDO (CHAVE ZERO)
        # ------------------------------------------------

        conexao.execute(text("""
            SET SESSION sql_mode =
            CONCAT(@@SESSION.sql_mode, ',NO_AUTO_VALUE_ON_ZERO')
        """))

        conexao.execute(text("""
            DELETE FROM dw_campo_real.dim_usina
            WHERE id_usina_origem = 0
        """))

        conexao.execute(text("""
            INSERT INTO dw_campo_real.dim_usina (
                usina_key, id_usina_origem, cod_usina, nome
            )
            VALUES (0, 0, 'DESCONHECIDA', 'Usina desconhecida')
        """))

        conexao.execute(text("""
            DELETE FROM dw_campo_real.dim_submercado
            WHERE codigo = 'UNK'
        """))

        conexao.execute(text("""
            INSERT INTO dw_campo_real.dim_submercado (
                submercado_key, codigo, nome
            )
            VALUES (0, 'UNK', 'Desconhecido')
        """))

        # ------------------------------------------------
        # 2. CARREGAR DIMENSÃO USINA
        # ------------------------------------------------

        conexao.execute(text("""
            INSERT INTO dw_campo_real.dim_usina (
                id_usina_origem,
                cod_usina,
                nome,
                id_fonte_origem,
                cod_submercado,
                uf,
                municipio,
                latitude,
                longitude,
                potencia_mw,
                data_inicio_operacao,
                situacao,
                descricao_fonte,
                renovavel,
                intermitente
            )
            SELECT
                u.id_usina,
                u.cod_usina,
                TRIM(u.nome),
                u.id_fonte,
                u.cod_submercado,
                u.uf,
                u.municipio,
                u.latitude,
                u.longitude,
                u.potencia_mw,
                u.data_inicio_operacao,
                u.situacao,
                f.descricao,
                f.renovavel,
                f.intermitente
            FROM campo_real_energia.usina u
            LEFT JOIN campo_real_energia.fonte_energia f
                ON f.id_fonte = u.id_fonte
            ON DUPLICATE KEY UPDATE
                cod_usina = VALUES(cod_usina),
                nome = VALUES(nome),
                id_fonte_origem = VALUES(id_fonte_origem),
                cod_submercado = VALUES(cod_submercado),
                uf = VALUES(uf),
                municipio = VALUES(municipio),
                latitude = VALUES(latitude),
                longitude = VALUES(longitude),
                potencia_mw = VALUES(potencia_mw),
                data_inicio_operacao = VALUES(data_inicio_operacao),
                situacao = VALUES(situacao),
                descricao_fonte = VALUES(descricao_fonte),
                renovavel = VALUES(renovavel),
                intermitente = VALUES(intermitente)
        """))

        # ------------------------------------------------
        # 3. CARREGAR DIMENSÃO SUBMERCADO
        # ------------------------------------------------

        conexao.execute(text("""
            INSERT INTO dw_campo_real.dim_submercado (codigo, nome)
            SELECT cod_submercado, nome
            FROM campo_real_energia.submercado
            ON DUPLICATE KEY UPDATE
                nome = VALUES(nome)
        """))

        # ------------------------------------------------
        # 4. IDENTIFICAR PERÍODO DO DW
        # ------------------------------------------------

        periodo = conexao.execute(text("""
            SELECT MIN(data_hora), MAX(data_hora)
            FROM (
                SELECT data_hora
                FROM campo_real_energia.geracao_tratada

                UNION ALL

                SELECT data_hora
                FROM campo_real_energia.clima_horario_api_tratado

                UNION ALL

                SELECT data_hora
                FROM campo_real_energia.pld_dw_tratado

                UNION ALL

                SELECT inicio AS data_hora
                FROM campo_real_energia.parada_dw_tratada

                UNION ALL

                SELECT fim AS data_hora
                FROM campo_real_energia.parada_dw_tratada
            ) AS datas
        """)).fetchone()

        inicio, fim = periodo

        if inicio is None or fim is None:
            raise ValueError("Não foram encontrados períodos para o DW.")

        inicio = inicio.replace(
            minute=0, second=0, microsecond=0
        )

        fim = fim.replace(
            minute=0, second=0, microsecond=0
        )

        # ------------------------------------------------
        # 5. CARREGAR FERIADOS
        # ------------------------------------------------

        feriados = set(
            linha[0]
            for linha in conexao.execute(text("""
                SELECT data
                FROM campo_real_energia.feriado_nacional
            """)).fetchall()
        )

        # ------------------------------------------------
        # 6. CRIAR DIMENSÃO TEMPO
        # ------------------------------------------------

        datas = set()
        atual = inicio

        while atual <= fim:
            datas.add(atual)
            atual += timedelta(hours=1)

        # Inclui horários exatos de início e fim das paradas.
        paradas = conexao.execute(text("""
            SELECT inicio, fim
            FROM campo_real_energia.parada_dw_tratada
        """)).fetchall()

        for parada in paradas:
            datas.add(parada[0])
            datas.add(parada[1])

        registros = []

        for data_hora in sorted(datas):

            data = data_hora.date()
            hora = data_hora.hour
            mes = data_hora.month

            if mes in [12, 1, 2]:
                estacao = "Verão"
            elif mes in [3, 4, 5]:
                estacao = "Outono"
            elif mes in [6, 7, 8]:
                estacao = "Inverno"
            else:
                estacao = "Primavera"

            if hora <= 6 or hora >= 22:
                patamar = "Leve"
            elif 18 <= hora <= 21:
                patamar = "Pesado"
            else:
                patamar = "Intermediário"

            registros.append({
                "tempo_key": int(data_hora.strftime("%Y%m%d%H")),
                "data_hora": data_hora,
                "data": data,
                "ano": data.year,
                "mes": data.month,
                "dia": data.day,
                "hora": hora,
                "dia_semana": data.weekday() + 1,
                "nome_dia": dias[data.weekday()],
                "fim_semana": data.weekday() >= 5,
                "feriado": data in feriados,
                "estacao": estacao,
                "patamar": patamar
            })

        conexao.execute(text("""
            INSERT IGNORE INTO dw_campo_real.dim_tempo (
                tempo_key,
                data_hora,
                data,
                ano,
                mes,
                dia,
                hora,
                dia_semana,
                nome_dia,
                fim_semana,
                feriado,
                estacao,
                patamar
            )
            VALUES (
                :tempo_key,
                :data_hora,
                :data,
                :ano,
                :mes,
                :dia,
                :hora,
                :dia_semana,
                :nome_dia,
                :fim_semana,
                :feriado,
                :estacao,
                :patamar
            )
        """), registros)

        print("\nDIMENSÕES CARREGADAS COM SUCESSO!")
        print(
            "Usinas:",
            conexao.execute(
               text("SELECT COUNT(*) FROM dw_campo_real.dim_usina")
            ).scalar()
        )
        print(
            "Submercados:",
            conexao.execute(
                text("SELECT COUNT(*) FROM dw_campo_real.dim_submercado")
            ).scalar()
        )
        print(
            "Horários:",
            conexao.execute(
                text("SELECT COUNT(*) FROM dw_campo_real.dim_tempo")
            ).scalar()
        )


if __name__ == "__main__":
    carregar_dimensoes()
