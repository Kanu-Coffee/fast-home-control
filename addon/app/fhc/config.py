import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator


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
        return self

    def azure_error(self):
        parts = (self.azure_api_key.get_secret_value(), self.azure_endpoint, self.azure_deployment)
        if not any(parts):
            return None
        if not all(parts):
            return "azure_configuration_incomplete"
        try:
            url = urlsplit(self.azure_endpoint)
            # Accessing port also validates malformed/non-numeric port strings.
            _ = url.port
            if (
                url.scheme != "https"
                or any(char.isspace() for char in self.azure_endpoint)
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
            ):
                return "azure_configuration_invalid"
        except ValueError:
            return "azure_configuration_invalid"
        return None

    def configured(self) -> list[str]:
        result = []
        if self.openrouter_api_key.get_secret_value():
            result.append("openrouter")
        if self.azure_api_key.get_secret_value() and not self.azure_error():
            result.append("azure")
        if self.provider in result:
            result.remove(self.provider)
            result.insert(0, self.provider)
        return result


def load_options() -> Options:
    path = Path(os.environ.get("FHC_OPTIONS_PATH", "/data/options.json"))
    try:
        return Options.model_validate(json.loads(path.read_text()) if path.exists() else {})
    except (ValidationError, ValueError, OSError):
        # Pydantic model-level errors can include the entire raw input, including keys.
        raise ValueError("invalid_app_options") from None
