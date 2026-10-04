import os
import sys
from pathlib import Path

# Settings() exige DATABASE_URL; os testes de inferência não tocam no banco.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://teste:teste@localhost:5432/teste")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
