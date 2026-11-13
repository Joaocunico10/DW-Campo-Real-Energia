
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from src.database import conectar_banco


PASTA = Path("data/entrada/clima")
ORIGEM = "https://archive-api.open-meteo.com/v1/archive"


def carregar_raw_clima():
    engine = conectar_banco()

    manifesto_path = PASTA / "manifesto_clima.json"

    with open(manifesto_path, "r", encoding="utf-8") as arquivo:
        manifesto = json.load(arquivo)

    with engine.begin() as conexao:
        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS raw_open_meteo (
                id_raw BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                nome_arquivo VARCHAR(255) NOT NULL,
                ids_usinas JSON NOT NULL,
                latitude DECIMAL(9,6) NOT NULL,
                longitude DECIMAL(9,6) NOT NULL,
                total_registros INT NOT NULL,
                conteudo_original LONGBLOB NOT NULL,
                origem VARCHAR(255) NOT NULL,
                extraido_em DATETIME NOT NULL,
                carregado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_arquivo (nome_arquivo)
            )
        """))

        total_carregado = 0

        for item in manifesto:
            caminho = PASTA / item["arquivo"]

            if not caminho.exists():
                print(f"Arquivo não encontrado: {caminho}")
                continue

            conteudo = caminho.read_bytes()

            # Usa a data de criação/modificação do arquivo como
            # referência do momento em que a resposta foi salva.
            extraido_em = datetime.fromtimestamp(
                caminho.stat().st_mtime
            )

            resultado = conexao.execute(
                text("""
                    INSERT IGNORE INTO raw_open_meteo (
                        nome_arquivo,
                        ids_usinas,
                        latitude,
                        longitude,
                        total_registros,
                        conteudo_original,
                        origem,
                        extraido_em
                    )
                    VALUES (
                        :nome_arquivo,
                        :ids_usinas,
                        :latitude,
                        :longitude,
                        :total_registros,
                        :conteudo_original,
                        :origem,
                        :extraido_em
                    )
                """),
                {
                    "nome_arquivo": item["arquivo"],
                    "ids_usinas": json.dumps(item["ids_usinas"]),
                    "latitude": item["latitude"],
                    "longitude": item["longitude"],
                    "total_registros": item["total_registros"],
                    "conteudo_original": conteudo,
                    "origem": ORIGEM,
                    "extraido_em": extraido_em
                }
            )

            if resultado.rowcount > 0:
                total_carregado += 1
                print(f"Carregado: {item['arquivo']}")
            else:
                print(f"Já existia: {item['arquivo']}")

    print(f"\nNovos arquivos carregados: {total_carregado}")


if __name__ == "__main__":
    carregar_raw_clima()
