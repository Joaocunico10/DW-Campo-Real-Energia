
from pathlib import Path
import pandas as pd


# Localiza a pasta principal do projeto
pasta_projeto = Path(__file__).resolve().parent.parent
pasta_dados = pasta_projeto / "data" / "entrada"

arquivos = [
    "pld_2025.csv",
    "pld_2026.csv"
]


def inspecionar_arquivo(nome_arquivo):
    caminho = pasta_dados / nome_arquivo

    print("\n" + "=" * 60)
    print(f"INSPECIONANDO: {nome_arquivo}")
    print("=" * 60)

    if not caminho.exists():
        print(f"ERRO: Arquivo não encontrado: {caminho}")
        return

    try:
        dados = pd.read_csv(
            caminho,
            sep=None,
            engine="python",
            encoding="utf-8-sig"
        )

    except UnicodeDecodeError:
        dados = pd.read_csv(
            caminho,
            sep=None,
            engine="python",
            encoding="latin1"
        )

    print(f"Tamanho: {caminho.stat().st_size / 1024:.2f} KB")
    print(f"Quantidade de registros: {len(dados)}")

    print("\nCOLUNAS:")
    for coluna in dados.columns:
        print(f"- {coluna}")

    print("\nTIPOS DE DADOS:")
    print(dados.dtypes)

    print("\nVALORES NULOS:")
    print(dados.isnull().sum())

    print("\nPRIMEIROS 5 REGISTROS:")
    print(dados.head().to_string(index=False))


def main():
    for arquivo in arquivos:
        inspecionar_arquivo(arquivo)


if __name__ == "__main__":
    main()
