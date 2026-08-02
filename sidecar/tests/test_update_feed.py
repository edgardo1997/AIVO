from pathlib import Path

from scripts.generate_update_feed import FEED_NAME, build, validate, write_feed


def test_build_feed_embeds_signature_and_url(tmp_path: Path):
    sig = tmp_path / "setup.exe.sig"
    sig.write_bytes(b"dW50cnVzdGVkIGNvbW1lbnQ6IHNpZ25hdHVyZQo=")
    feed = build(
        version="1.0.0",
        installer_url="https://example.test/releases/download/v1.0.0/Sentinel-setup.exe",
        signature_file=sig,
        root=tmp_path,
    )
    validate(feed)
    target = write_feed(tmp_path, feed)
    assert target.name == FEED_NAME
    assert target.is_file()
    platform = feed["platforms"]["windows-x86_64"]
    assert platform["url"].endswith("Sentinel-setup.exe")
    assert platform["signature"] and len(platform["signature"]) > 0


def test_build_feed_rejects_missing_signature(tmp_path: Path):
    import pytest

    with pytest.raises(ValueError):
        build(
            version="1.0.0",
            installer_url="https://example.com/update.exe",
            signature_file=tmp_path / "missing.sig",
            root=tmp_path,
        )


def test_validate_rejects_bad_feed():
    import pytest

    with pytest.raises(ValueError):
        validate({"version": "1.0.0", "platforms": {"windows-x86_64": {"url": "x"}}})

    with pytest.raises(ValueError):
        validate({})
