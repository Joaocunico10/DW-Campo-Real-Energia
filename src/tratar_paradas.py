
from sqlalchemy import text

from src.database import conectar_banco


def tratar_paradas():
    engine = conectar_banco()

    with engine.begin() as conexao:

        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS parada_dw_tratada (
                id_parada INT PRIMARY KEY,
                id_usina INT NOT NULL,
                inicio DATETIME NOT NULL,
                fim DATETIME NOT NULL,
                tipo VARCHAR(20) NOT NULL,
                motivo VARCHAR(120) NOT NULL,
                duracao_horas DECIMAL(10,2) NOT NULL
            )
        """))

        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS parada_dw_quarentena (
                id_parada INT PRIMARY KEY,
                id_usina INT,
                inicio DATETIME,
                fim DATETIME,
                tipo VARCHAR(20),
                motivo VARCHAR(120),
                motivo_quarentena VARCHAR(255) NOT NULL
            )
        """))

        # Limpa somente as tabelas derivadas.
        conexao.execute(text("DELETE FROM parada_dw_tratada"))
        conexao.execute(text("DELETE FROM parada_dw_quarentena"))

        # Identifica intervalos inválidos e referências inexistentes.
        conexao.execute(text("""
            INSERT INTO parada_dw_quarentena (
                id_parada, id_usina, inicio, fim,
                tipo, motivo, motivo_quarentena
            )
            SELECT
                p.id_parada,
                p.id_usina,
                p.inicio,
                p.fim,
                p.tipo,
                p.motivo,
                CASE
                    WHEN p.fim <= p.inicio
                        THEN 'Data final anterior ou igual à inicial'
                    WHEN u.id_usina IS NULL
                        THEN 'Usina não cadastrada'
                    ELSE 'Registro inválido'
                END
            FROM parada_usina p
            LEFT JOIN usina u ON u.id_usina = p.id_usina
            WHERE p.fim <= p.inicio
               OR u.id_usina IS NULL
        """))

        # Copia somente as paradas válidas.
        conexao.execute(text("""
            INSERT INTO parada_dw_tratada (
                id_parada, id_usina, inicio, fim,
                tipo, motivo, duracao_horas
            )
            SELECT
                p.id_parada,
                p.id_usina,
                p.inicio,
                p.fim,
                p.tipo,
                p.motivo,
                TIMESTAMPDIFF(MINUTE, p.inicio, p.fim) / 60.0
            FROM parada_usina p
            INNER JOIN usina u ON u.id_usina = p.id_usina
            WHERE p.fim > p.inicio
        """))

        tratados = conexao.execute(
            text("SELECT COUNT(*) FROM parada_dw_tratada")
        ).scalar()

        quarentena = conexao.execute(
            text("SELECT COUNT(*) FROM parada_dw_quarentena")
        ).scalar()

        print("\nTRATAMENTO DAS PARADAS FINALIZADO")
        print(f"Registros tratados: {tratados}")
        print(f"Registros em quarentena: {quarentena}")


if __name__ == "__main__":
    tratar_paradas()
