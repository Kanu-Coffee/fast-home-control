import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator


class Options(BaseModel):
    model_config = ConfigDict(extra="ignore")
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = "microsoft/microsoft-decision-1"
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
        if not self.openrouter_model or self.openrouter_model.isspace():
            self.openrouter_model = "microsoft/microsoft-decision-1"
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

    def public_dict(self) -> dict:
        return {
            "openrouter_configured": bool(self.openrouter_api_key.get_secret_value()),
            "openrouter_model": self.openrouter_model,
            "azure_configured": bool(self.azure_api_key.get_secret_value()),
            "azure_endpoint": self.azure_endpoint,
            "azure_deployment": self.azure_deployment,
            "azure_error": self.azure_error(),
            "provider": self.provider,
            "rescan_hours": self.rescan_hours,
            "history_days": self.history_days,
            "history_limit": self.history_limit,
            "configured_providers": self.configured(),
        }

    def raw_options(self) -> dict:
        return {
            "openrouter_api_key": self.openrouter_api_key.get_secret_value(),
            "openrouter_model": self.openrouter_model,
            "azure_api_key": self.azure_api_key.get_secret_value(),
            "azure_endpoint": self.azure_endpoint,
            "azure_deployment": self.azure_deployment,
            "provider": self.provider,
            "rescan_hours": self.rescan_hours,
            "history_days": self.history_days,
            "history_limit": self.history_limit,
        }


def load_options() -> Options:
    path = Path(os.environ.get("FHC_OPTIONS_PATH", "/data/options.json"))
    try:
        return Options.model_validate(json.loads(path.read_text()) if path.exists() else {})
    except (ValidationError, ValueError, OSError):
        # Pydantic model-level errors can include the entire raw input, including keys.
        raise ValueError("invalid_app_options") from None


async def supervisor_options(client):
    response = await client.get(
        "http://supervisor/addons/self/info",
        headers={"Authorization": "Bearer " + os.environ.get("SUPERVISOR_TOKEN", "")},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("result") != "ok" or not isinstance(
        payload.get("data", {}).get("options"), dict
    ):
        raise ValueError("supervisor_options_read_failed")
    return payload["data"]["options"]


async def read_public_options(current):
    if os.environ.get("FHC_STANDALONE_TOKEN"):
        path = Path(os.environ.get("FHC_OPTIONS_PATH", "/data/options.json"))
        return await asyncio.to_thread(lambda: load_options() if path.exists() else current)
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            return Options.model_validate(await supervisor_options(client))
    except (httpx.HTTPError, ValueError, TypeError):
        raise ValueError("options_read_failed") from None


async def save_options(updates: dict, current: Options | None = None) -> Options:
    import tempfile

    import httpx

    standalone = bool(os.environ.get("FHC_STANDALONE_TOKEN"))
    if not standalone and not os.environ.get("SUPERVISOR_TOKEN"):
        raise ValueError("supervisor_token_missing")
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            if standalone:
                path = Path(os.environ.get("FHC_OPTIONS_PATH", "/data/options.json"))

                def read_current():
                    return (
                        json.loads(path.read_text())
                        if path.exists()
                        else (current or Options()).raw_options()
                    )

                data = await asyncio.to_thread(read_current)
            else:
                data = await supervisor_options(client)
            data = dict(data)
            for key, value in updates.items():
                if key.startswith("delete_") or value is None:
                    continue
                if key in {"openrouter_api_key", "azure_api_key"}:
                    if value.strip():
                        data[key] = value.strip()
                else:
                    data[key] = value.strip() if isinstance(value, str) else value
            for key in ("openrouter_api_key", "azure_api_key"):
                if updates.get("delete_" + key):
                    data[key] = ""
            new_options = Options.model_validate(data)
            # Known fields get validated/defaulted; preserve unrelated canonical options.
            data.update(new_options.raw_options())
            if not standalone:
                resp = await client.post(
                    "http://supervisor/addons/self/options",
                    headers={"Authorization": "Bearer " + os.environ["SUPERVISOR_TOKEN"]},
                    json={"options": data},
                )
                resp.raise_for_status()
                if resp.json().get("result") != "ok":
                    raise ValueError("supervisor_options_update_failed")
            else:

                def persist():
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    fd, name = tempfile.mkstemp(prefix=".options-", dir=path.parent)
                    try:
                        with os.fdopen(fd, "w") as output:
                            json.dump(data, output, ensure_ascii=False)
                            output.flush()
                            os.fsync(output.fileno())
                        os.replace(name, path)
                    finally:
                        if os.path.exists(name):
                            os.unlink(name)

                await asyncio.to_thread(persist)
    except (httpx.HTTPError, ValueError, OSError, TypeError, KeyError):
        raise ValueError("options_save_failed") from None
    return new_options
