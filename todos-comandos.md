Comando	O que faz
uv init --bare	Cria o pyproject.toml
uv add <pacote>	Adiciona uma biblioteca
uv sync	Prepara o ambiente a partir do lock
uv run python -m pipeline.ingestao	CSV → raw
uv run python -m pipeline.transformacao	raw → refined
uv run python -m pipeline.marts	refined → marts
uv run python executar.py	Tudo do zero
uv run python ui.py	Sobe o notebook SQL do DuckDB em localhost:4213
uv run streamlit run app.py	Abre o dashboard
uv run pytest	Roda os testes
uv run ruff check .	Confere o estilo do código
uv run python -X utf8 ...	Idem, com acentos e tabelas corretos no Windows