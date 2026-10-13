import json
import traceback

import pytest
from fhc.config import Options, load_options


def test_invalid_config_does_not_expose_keys_in_startup_traceback(tmp_path, monkeypatch):
    path = tmp_path / "options.json"
    secret = "private-test-credential"
    path.write_text(json.dumps({"openrouter_api_key": secret, "provider": "invalid"}))
    monkeypatch.setenv("FHC_OPTIONS_PATH", str(path))
    with pytest.raises(ValueError, match="invalid_app_options") as caught:
        load_options()
    assert secret not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://bad",
        "https://bad/path",
        "https://user:pass@bad",
        "https://[",
        "https://bad:port",
        "https://bad host",
    ],
)
def test_invalid_azure_is_isolated_from_valid_openrouter(endpoint):
    options = Options(
        openrouter_api_key="test-only",
        azure_api_key="unused",
        azure_endpoint=endpoint,
        azure_deployment="unused",
        provider="azure",
    )
    assert options.azure_error() == "azure_configuration_invalid"
    assert options.configured() == ["openrouter"]


def test_partial_azure_does_not_block_openrouter_or_count_as_configured():
    options = Options(openrouter_api_key="test-only", azure_api_key="unused")
    assert options.azure_error() == "azure_configuration_incomplete"
    assert options.configured() == ["openrouter"]


def test_openrouter_model_default_and_custom():
    opts = Options()
    assert opts.openrouter_model == "microsoft/microsoft-decision-1"
    custom = Options(openrouter_model="custom/model-id")
    assert custom.openrouter_model == "custom/model-id"


def test_public_dict_does_not_reveal_secrets():
    opts = Options(
        openrouter_api_key="super-secret-openrouter-key",
        azure_api_key="super-secret-azure-key",
        azure_endpoint="https://myresource.openai.azure.com/",
        azure_deployment="my-dep",
    )
    pub = opts.public_dict()
    assert pub["openrouter_configured"] is True
    assert pub["azure_configured"] is True
    assert "super-secret" not in json.dumps(pub)
    assert pub["openrouter_model"] == "microsoft/microsoft-decision-1"


async def test_save_options_persists_to_file(tmp_path, monkeypatch):
    from fhc.config import save_options

    path = tmp_path / "options.json"
    monkeypatch.setenv("FHC_OPTIONS_PATH", str(path))
    monkeypatch.setenv("FHC_STANDALONE_TOKEN", "test-token")

    initial = Options(openrouter_api_key="initial-key")
    path.write_text(json.dumps(initial.raw_options()))

    updated = await save_options(
        {"openrouter_model": "new/model", "provider": "openrouter"},
        current=initial,
    )
    assert updated.openrouter_model == "new/model"
    assert updated.openrouter_api_key.get_secret_value() == "initial-key"
    assert updated.provider == "openrouter"

    saved_data = json.loads(path.read_text())
    assert saved_data["openrouter_model"] == "new/model"
    assert saved_data["openrouter_api_key"] == "initial-key"
