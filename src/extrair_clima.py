
import json
import time
from pathlib import Path

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.database import conectar_banco


URL = "https://archive-api.open-meteo.com/v1/archive"

VARIAVEIS = [
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "shortwave_radiation"
]


@retry(
    retry=retry_if_exception_type(
        (requests.Timeout, requests.ConnectionError)
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10)
)
def consultar_clima(latitude, longitude):
    parametros = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": "2025-01-01",
        "end_date": "2026-11-13",
        "hourly": VARIAVEIS,
        "timezone": "America/Sao_Paulo"
    }

    resposta = requests.get(URL, params=parametros, timeout=120)
    resposta.raise_for_status()

    return resposta.content


def extrair_clima():
    pasta_saida = Path("data/entrada/clima")
    pasta_saida.mkdir(parents=True, exist_ok=True)

    engine = conectar_banco()

    usinas = pd.read_sql(
        """
        SELECT id_usina, cod_usina, latitude, longitude
        FROM usina
        WHERE latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY id_usina
        """,
        engine
    )

    coordenadas = usinas.drop_duplicates(
        subset=["latitude", "longitude"]
    )

    print(f"Usinas encontradas: {len(usinas)}")
    print(f"Localizações únicas: {len(coordenadas)}")

    manifesto = []

    for numero, (_, local) in enumerate(coordenadas.iterrows(), start=1):
        latitude = float(local["latitude"])
        longitude = float(local["longitude"])

        usinas_local = usinas[
            (usinas["latitude"] == local["latitude"]) &
            (usinas["longitude"] == local["longitude"])
        ]

        ids_usinas = usinas_local["id_usina"].astype(int).tolist()

        nome_arquivo = (
            f"clima_usinas_{'_'.join(map(str, ids_usinas))}.json"
        )

        caminho = pasta_saida / nome_arquivo

        print(
            f"\n[{numero}/{len(coordenadas)}] "
            f"Consultando usina(s): {ids_usinas}"
        )

        if caminho.exists():
            print("Arquivo já existe. Pulando consulta.")
            continue

        try:
            conteudo = consultar_clima(latitude, longitude)

            # Guarda a resposta original da API, sem transformar o JSON.
            caminho.write_bytes(conteudo)

            dados = json.loads(conteudo)

            manifesto.append({
                "arquivo": nome_arquivo,
                "ids_usinas": ids_usinas,
                "latitude": latitude,
                "longitude": longitude,
                "primeiro_horario": dados["hourly"]["time"][0],
                "ultimo_horario": dados["hourly"]["time"][-1],
                "total_registros": len(dados["hourly"]["time"])
            })

            print(
                f"Salvo: {len(dados['hourly']['time'])} "
                "registros horários."
            )

            time.sleep(1)

        except (requests.RequestException, KeyError, ValueError) as erro:
            print(f"Erro na consulta: {erro}")

    caminho_manifesto = pasta_saida / "manifesto_clima.json"

    caminho_manifesto.write_text(
        json.dumps(manifesto, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\nExtração finalizada!")
    print(f"Arquivos salvos em: {pasta_saida}")


if __name__ == "__main__":
    extrair_clima()
