
import requests


URL = "https://archive-api.open-meteo.com/v1/archive"


def testar_open_meteo():
    parametros = {
        "latitude": -30.890000,
        "longitude": -55.530000,
        "start_date": "2025-01-01",
        "end_date": "2026-11-13",
        "hourly": [
            "temperature_2m",
            "precipitation",
            "wind_speed_10m",
            "shortwave_radiation"
        ],
        "timezone": "America/Sao_Paulo"
    }

    try:
        resposta = requests.get(
            URL,
            params=parametros,
            timeout=60
        )

        resposta.raise_for_status()
        dados = resposta.json()

        horas = dados["hourly"]["time"]

        print("Conexão com Open-Meteo realizada!")
        print("Local:", dados["latitude"], dados["longitude"])
        print("Registros horários:", len(horas))
        print("Primeiro registro:", horas[0])
        print("Último registro:", horas[-1])

        print("\nPrimeiros dados:")
        for i in range(min(5, len(horas))):
            print(
                horas[i],
                "| Temperatura:",
                dados["hourly"]["temperature_2m"][i],
                "| Vento:",
                dados["hourly"]["wind_speed_10m"][i]
            )

    except requests.RequestException as erro:
        print("Erro na consulta meteorológica:", erro)


if __name__ == "__main__":
    testar_open_meteo()
