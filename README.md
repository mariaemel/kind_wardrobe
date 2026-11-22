# «Добрый шкаф» — backend

## Локальный запуск

### Windows (Git Bash)

```bash
cp .env.example .env
py -3.12 -m venv .venv
source .venv/Scripts/activate
pip install -r requirements-dev.txt

docker compose up -d db
docker compose exec db pg_isready -U kind_wardrobe -d kind_wardrobe

alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```


### macOS / Linux

```bash
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

docker compose up -d db
docker compose exec db pg_isready -U kind_wardrobe -d kind_wardrobe

alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

После запуска:

- Swagger: http://127.0.0.1:8000/docs
