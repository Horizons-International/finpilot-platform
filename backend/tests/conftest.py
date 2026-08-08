import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://user:123789@localhost:5432/customers",
)

os.environ.setdefault(
    "SECRET_KEY",
    "test-secret-key",
)
