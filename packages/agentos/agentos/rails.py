"""Credentials for rails that are not the core Stellar settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class RailCredentials(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTOS_", env_file=".env", extra="ignore")

    evm_rpc_url: str = ""
    pollar_api_key: str = ""
    pollar_api_base: str = "https://server.api.pollar.xyz/v3"
    trustless_work_api_key: str = ""
    trustless_work_api_base: str = "https://dev.api.trustlesswork.com"


def get_rail_credentials() -> RailCredentials:
    return RailCredentials()
