
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from src.database import conectar_banco


PASTA = Path("data/entrada/clima")


def carregar_clima_tratado():
    engine = conectar_banco()

    manifesto_path = PASTA / "manifesto_clima.json"

    with open(manifesto_path, "r", encoding="utf-8") as arquivo:
        manifesto = json.load(arquivo)

    todos_dados = []

    for item in manifesto:
        caminho = PASTA / item["arquivo"]

        print(f"Lendo: {item['arquivo']}")

        with open(caminho, "r", encoding="utf-8") as arquivo:
            resposta = json.load(arquivo)

        horario = resposta["hourly"]

        dados = pd.DataFrame({
            "data_hora": pd.to_datetime(horario["time"]),
            "temperatura": horario["temperature_2m"],
            "precipitacao": horario["precipitation"],
            "velocidade_vento": horario["wind_speed_10m"],
            "radiacao_solar": horario["shortwave_radiation"]
        })

        dados["latitude"] = item["latitude"]
        dados["longitude"] = item["longitude"]

        for id_usina in item["ids_usinas"]:
            dados_usina = dados.copy()
            dados_usina["id_usina"] = id_usina
            todos_dados.append(dados_usina)

    df = pd.concat(todos_dados, ignore_index=True)

    print("\nTotal de registros preparados:", len(df))

    with engine.begin() as conexao:
        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS clima_horario_api_tratado (
                id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                id_usina INT NOT NULL,
                data_hora DATETIME NOT NULL,
                temperatura DECIMAL(6,2),
                precipitacao DECIMAL(8,2),
                velocidade_vento DECIMAL(8,2),
                radiacao_solar DECIMAL(10,2),
                latitude DECIMAL(9,6) NOT NULL,
                longitude DECIMAL(9,6) NOT NULL,
                origem VARCHAR(100) NOT NULL,
                UNIQUE KEY uq_clima_usina_hora (id_usina, data_hora),
                INDEX idx_clima_data (data_hora),
                INDEX idx_clima_usina (id_usina)
            )
        """))

    df["origem"] = "Open-Meteo Archive API"

    df.to_sql(
        name="clima_horario_api_tratado",
        con=engine,
        if_exists="append",
        index=False,
        chunksize=5000,
        method="multi"
    )

    print("\nCarga do clima tratado concluída!")


if __name__ == "__main__":
    carregar_clima_tratado()
