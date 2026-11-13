
from pathlib import Path
from datetime import datetime, timezone
import hashlib

from sqlalchemy import text

from src.database import conectar_banco


PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_ENTRADA = PASTA_PROJETO / "data" / "entrada"

ARQUIVOS = [
    "pld_2025.csv",
    "pld_2026.csv"
]

ORIGEM = "Portal Dados Abertos da CCEE - PLD_HORARIO"


def criar_tabela_raw(conexao):
    sql = """
    CREATE TABLE IF NOT EXISTS raw_ccee_pld (
        id_raw BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        nome_arquivo VARCHAR(255) NOT NULL,
        numero_linha INT UNSIGNED NOT NULL,
        hash_arquivo CHAR(64) NOT NULL,
        conteudo_original LONGBLOB NOT NULL,
        origem VARCHAR(255) NOT NULL,
        extraido_em DATETIME(6) NOT NULL,
        UNIQUE KEY uq_arquivo_linha (hash_arquivo, numero_linha)
    )
    """

    conexao.execute(text(sql))


def carregar_arquivo(conexao, nome_arquivo):
    caminho = PASTA_ENTRADA / nome_arquivo

    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    conteudo = caminho.read_bytes()
    hash_arquivo = hashlib.sha256(conteudo).hexdigest()

    linhas = conteudo.splitlines(keepends=True)
    data_extracao = datetime.now(timezone.utc).replace(tzinfo=None)

    registros = []

    for numero, linha in enumerate(linhas, start=1):
        registros.append({
            "nome_arquivo": nome_arquivo,
            "numero_linha": numero,
            "hash_arquivo": hash_arquivo,
            "conteudo_original": linha,
            "origem": ORIGEM,
            "extraido_em": data_extracao
        })

    sql = text("""
        INSERT IGNORE INTO raw_ccee_pld (
            nome_arquivo,
            numero_linha,
            hash_arquivo,
            conteudo_original,
            origem,
            extraido_em
        )
        VALUES (
            :nome_arquivo,
            :numero_linha,
            :hash_arquivo,
            :conteudo_original,
            :origem,
            :extraido_em
        )
    """)

    inseridos = 0

    for inicio in range(0, len(registros), 1000):
        lote = registros[inicio:inicio + 1000]
        resultado = conexao.execute(sql, lote)
        inseridos += resultado.rowcount

    print(f"\nArquivo: {nome_arquivo}")
    print(f"Linhas originais: {len(linhas)}")
    print(f"Novas linhas gravadas: {inseridos}")
    print(f"SHA-256: {hash_arquivo}")


def main():
    engine = conectar_banco()

    try:
        with engine.begin() as conexao:
            criar_tabela_raw(conexao)

            for arquivo in ARQUIVOS:
                carregar_arquivo(conexao, arquivo)

            total = conexao.execute(
                text("SELECT COUNT(*) FROM raw_ccee_pld")
            ).scalar()

            print("\n===================================")
            print("CARGA RAW CONCLUÍDA!")
            print(f"Total de linhas armazenadas: {total}")
            print("===================================")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
