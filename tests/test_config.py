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
