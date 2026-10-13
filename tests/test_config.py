import json
import traceback

import pytest
from fhc.config import load_options


def test_invalid_config_does_not_expose_keys_in_startup_traceback(tmp_path, monkeypatch):
    path = tmp_path / "options.json"
    secret = "private-test-credential"
    path.write_text(json.dumps({"openrouter_api_key": secret, "azure_endpoint": "http://bad"}))
    monkeypatch.setenv("FHC_OPTIONS_PATH", str(path))
    with pytest.raises(ValueError, match="invalid_app_options") as caught:
        load_options()
    assert secret not in "".join(traceback.format_exception(caught.value))
