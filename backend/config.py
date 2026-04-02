from pathlib import Path

OLLAMA_BASE = "http://localhost:11434"
DB_PATH = Path(__file__).parent.parent / "deepfrida.db"
DEFAULT_MODEL = "deepseek-r1:14b"
