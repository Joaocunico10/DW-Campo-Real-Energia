
from pathlib import Path
import pandas as pd


PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_ENTRADA = PASTA_PROJETO / "data" / "entrada"
PASTA_TRATADA = PASTA_PROJETO / "data" / "tratada"

ARQUIVOS = ["pld_2025.csv", "pld_2026.csv"]

SUBMERCADOS_VALIDOS = [
    "NORTE",
    "NORDESTE",
    "SUL",
    "SUDESTE"
]


def carregar_arquivo(nome):
    caminho = PASTA_ENTRADA / nome

    return pd.read_csv(
        caminho,
        sep=None,
        engine="python",
        encoding="utf-8-sig"
    )


def tratar_arquivo(nome):
    dados = carregar_arquivo(nome)

    # Padroniza os nomes dos submercados
    dados["SUBMERCADO"] = (
        dados["SUBMERCADO"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Constrói a data completa a partir do mês, dia e hora
    data_base = pd.to_datetime(
        dados["MES_REFERENCIA"].astype(str).str.zfill(6)
        + dados["DIA"].astype(str).str.zfill(2),
        format="%Y%m%d",
        errors="coerce"
    )

    dados["DATA_HORA"] = (
        data_base + pd.to_timedelta(dados["HORA"], unit="h")
    )

    # Validações
    if dados["DATA_HORA"].isna().any():
        raise ValueError(f"Datas inválidas encontradas em {nome}")

    if not dados["SUBMERCADO"].isin(SUBMERCADOS_VALIDOS).all():
        raise ValueError(f"Submercado desconhecido em {nome}")

    if not dados["HORA"].between(0, 23).all():
        raise ValueError(f"Horários inválidos em {nome}")

    # Confere se existem registros duplicados
    duplicados = dados.duplicated(
        subset=["DATA_HORA", "SUBMERCADO"]
    ).sum()

    if duplicados > 0:
        raise ValueError(
            f"{duplicados} registros duplicados encontrados em {nome}"
        )

    # Confere o ano de origem
    ano_esperado = int(nome[4:8])

    if not (dados["DATA_HORA"].dt.year == ano_esperado).all():
        raise ValueError(f"Registros de ano incorreto em {nome}")

    return dados


def main():
    PASTA_TRATADA.mkdir(parents=True, exist_ok=True)

    arquivos_tratados = []

    for arquivo in ARQUIVOS:
        print(f"\nTratando {arquivo}...")

        dados = tratar_arquivo(arquivo)

        print(f"Registros: {len(dados)}")
        print("Registros por submercado:")
        print(dados["SUBMERCADO"].value_counts().to_string())

        arquivos_tratados.append(dados)

    resultado = pd.concat(
        arquivos_tratados,
        ignore_index=True
    )

    resultado = resultado.sort_values(
        ["DATA_HORA", "SUBMERCADO"]
    )

    caminho_saida = PASTA_TRATADA / "pld_horario_2025_2026.csv"

    resultado.to_csv(
        caminho_saida,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n" + "=" * 50)
    print("TRATAMENTO CONCLUÍDO!")
    print(f"Total de registros: {len(resultado)}")
    print(f"Arquivo salvo em: {caminho_saida}")
    print("=" * 50)


if __name__ == "__main__":
    main()
