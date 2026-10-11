# «Добрый шкаф» — backend

## Локальный запуск

### Bash

```bash
cp .env.example .env
docker compose up -d db

python3.12 -m venv .venv
source .venv/Scripts/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### PowerShell (Windows)

```powershell
Copy-Item .env.example .env
docker compose up -d db

py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\uvicorn app.main:app --reload
```

После запуска:

- Swagger: http://localhost:8000/docs

