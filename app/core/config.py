from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # DB
    DATABASE_URL: str

    # JWT config (names MUST match what your code uses)
    JWT_SECRET: str = "changeme"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()