import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class Options(BaseModel):
    model_config = ConfigDict(extra="ignore")
    openrouter_api_key: SecretStr = SecretStr("")
    azure_api_key: SecretStr = SecretStr("")
    azure_endpoint: str = ""
    azure_deployment: str = ""
    provider: str = "auto"
    rescan_hours: int = Field(default=12, ge=1, le=168)
    history_days: int = Field(default=7, ge=1, le=30)
    history_limit: int = Field(default=1000, ge=10, le=10000)

    @model_validator(mode="after")
    def validate_provider(self):
        if self.provider not in {"auto", "openrouter", "azure"}:
            raise ValueError("invalid provider")
        if self.azure_endpoint:
            from urllib.parse import urlsplit

            url = urlsplit(self.azure_endpoint)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
            ):
                raise ValueError("Azure endpoint must be an HTTPS resource origin")
        return self

    def configured(self) -> list[str]:
        result = []
        if self.openrouter_api_key.get_secret_value():
            result.append("openrouter")
        if self.azure_api_key.get_secret_value() and self.azure_endpoint and self.azure_deployment:
            result.append("azure")
        if self.provider in result:
            result.remove(self.provider)
            result.insert(0, self.provider)
        return result


def load_options() -> Options:
    path = Path(os.environ.get("FHC_OPTIONS_PATH", "/data/options.json"))
    return Options.model_validate(json.loads(path.read_text()) if path.exists() else {})
