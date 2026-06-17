"""Documentation assets stay wired into the public READMEs."""

from pathlib import Path

ROOT = Path(__file__).parent.parent
ARCHITECTURE_ASSET = "docs/assets/trustband-architecture.svg"


def test_architecture_asset_is_referenced_by_readmes():
    asset = ROOT / ARCHITECTURE_ASSET
    assert asset.exists()
    assert ARCHITECTURE_ASSET in (ROOT / "README.md").read_text()
    assert ARCHITECTURE_ASSET in (ROOT / "README_EN.md").read_text()
