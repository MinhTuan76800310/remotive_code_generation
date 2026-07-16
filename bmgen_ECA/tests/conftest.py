from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def schema_v2_path() -> Path:
    return FIXTURES / "schema_v2.yaml"
