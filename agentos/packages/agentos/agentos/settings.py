from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTOS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://agentos:agentos@127.0.0.1:5433/agentos"
    bootstrap_token: str = "change-me-lab-only"
    env: str = "lab"
    auto_allow_amount_max: str = "10"
    # Lab-only Stellar Testnet signer — never persist in DB
    stellar_horizon_url: str = "https://horizon-testnet.stellar.org"
    stellar_network_passphrase: str = "Test SDF Network ; September 2015"
    stellar_secret_key: str = ""
    oauth_signing_key: str = "lab-only-change-me-32b-min-key!!"
    oauth_token_ttl_seconds: int = 900


def get_settings() -> Settings:
    return Settings()
