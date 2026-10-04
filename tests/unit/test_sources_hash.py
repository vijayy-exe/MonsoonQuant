from pathlib import Path

from mq.specs.sources import sha256_of, store_raw_file


def test_sha256_of_matches_known_digest(tmp_path: Path) -> None:
    f = tmp_path / "doc.txt"
    f.write_bytes(b"hello monsoon")
    # sha256("hello monsoon")
    expected = "e59a049df72f4ec0c9f5c80140dc9fc8eb2958366641b136635013d990b38b24"
    assert sha256_of(f) == expected


def test_store_raw_file_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    src = tmp_path / "a.pdf"
    src.write_bytes(b"contract spec v1")

    digest1, path1 = store_raw_file(src, raw_dir=raw_dir)
    assert path1.exists()
    assert path1.name == f"{digest1}.pdf"

    # Re-registering identical content must not raise and must resolve to
    # the same object, never overwriting it.
    digest2, path2 = store_raw_file(src, raw_dir=raw_dir)
    assert digest1 == digest2
    assert path1 == path2


def test_store_raw_file_never_overwrites_existing_object(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    src = tmp_path / "a.pdf"
    src.write_bytes(b"original content")
    _, path = store_raw_file(src, raw_dir=raw_dir)
    mtime_before = path.stat().st_mtime_ns

    # Even if the source file is later modified and re-pointed at the same
    # (now stale) digest path by a buggy caller, store_raw_file should not
    # clobber an existing object for a *different* digest's filename — this
    # test just pins down that re-registering unmodified content is a no-op.
    store_raw_file(src, raw_dir=raw_dir)
    assert path.stat().st_mtime_ns == mtime_before
