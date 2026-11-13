from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from src.config import (
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD
)


def conectar_banco():
    url = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME
    )

    engine = create_engine(url)

    return engine


def testar_conexao():
    try:
        engine = conectar_banco()

        with engine.connect() as conexao:
            resultado = conexao.execute(text("SELECT DATABASE()"))

            banco = resultado.scalar()

            print("Conexão realizada com sucesso!")
            print(f"Banco conectado: {banco}")

        engine.dispose()

    except Exception as erro:
        print("Erro ao conectar com o banco:")
        print(erro)