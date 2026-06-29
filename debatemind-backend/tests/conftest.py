import os

# Provide required settings so modules can be imported without a .env file.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters!")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
