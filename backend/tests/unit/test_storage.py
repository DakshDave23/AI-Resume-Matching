from pathlib import Path

import pytest

from app.core.config import BACKEND_DIR, Settings
from app.services.storage import FileStore
from app.services.uploads import display_name


def test_files_are_saved_under_uuid_names(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "uploads")
    name = store.save(b"%PDF-1.7 ...", "pdf")

    assert name.endswith(".pdf") and len(name) == 36 + 4
    assert store.read(name) == b"%PDF-1.7 ..."
    assert [p.name for p in (tmp_path / "uploads").iterdir()] == [name]  # no .part left over
    assert store.save(b"%PDF-1.7 ...", "pdf") != name  # same bytes, new name


def test_deleting_is_safe_to_repeat(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    name = store.save(b"data", "docx")
    store.delete(name)
    store.delete(name)
    assert not store.path(name).exists()


@pytest.mark.parametrize(
    "name",
    ["../../etc/passwd", "cv.pdf", "0b0e2c5e-0000-4000-8000-000000000000.exe", "", "a/b.pdf"],
)
def test_only_stored_names_become_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="not a stored file name"):
        FileStore(tmp_path).path(name)


def test_a_relative_upload_dir_is_under_the_backend_folder(tmp_path: Path) -> None:
    relative = FileStore.from_settings(Settings(upload_dir=Path("storage/uploads")))
    assert relative.root == (BACKEND_DIR / "storage" / "uploads").resolve()
    assert FileStore.from_settings(Settings(upload_dir=tmp_path)).root == tmp_path


@pytest.mark.parametrize(
    ("sent", "shown"),
    [
        ("cv.pdf", "cv.pdf"),
        ("C:\\Users\\asha\\Desktop\\cv.pdf", "cv.pdf"),  # old browsers send the full path
        ("/home/asha/cv.docx", "cv.docx"),
        ("../../secret.pdf", "secret.pdf"),
        ("   ", "resume"),
        ("x" * 300 + ".pdf", "x" * 254 + "…"),
    ],
)
def test_display_names_drop_folders(sent: str, shown: str) -> None:
    assert display_name(sent) == shown
