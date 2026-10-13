"""
Unit tests for Scoped File Search and Dictation / Text Insertion handlers.
"""

from pathlib import Path
import pytest

from src.agent.policy_engine import PolicyEngine
from src.agent.tools.handlers.dictation import insert_text
from src.agent.tools.handlers.file_search import search_files
from src.agent.tools.models import ExecutionStatus


def test_file_search_within_authorized_folder(tmp_path: Path):
    auth_dir = tmp_path / "my_project"
    auth_dir.mkdir()

    (auth_dir / "main.py").write_text("print('hello')")
    (auth_dir / "utils.py").write_text("def helper(): pass")
    (auth_dir / "notes.txt").write_text("Meeting notes")

    engine = PolicyEngine(authorized_roots=[auth_dir])

    # 1. Search by pattern
    res_pat = search_files(pattern="utils", root_dir=str(auth_dir), policy_engine=engine)
    assert res_pat.success is True
    assert res_pat.result["count"] == 1
    assert res_pat.result["results"][0]["name"] == "utils.py"

    # 2. Search by extension
    res_ext = search_files(pattern="", extension="py", root_dir=str(auth_dir), policy_engine=engine)
    assert res_ext.success is True
    assert res_ext.result["count"] == 2

    # 3. Search outside authorized root rejected
    forbidden_dir = tmp_path / "other_folder"
    forbidden_dir.mkdir()
    res_forbid = search_files(pattern="test", root_dir=str(forbidden_dir), policy_engine=engine)
    assert res_forbid.success is False
    assert "Access Denied" in res_forbid.error


def test_file_search_skips_internal_caches(tmp_path: Path):
    auth_dir = tmp_path / "project_with_cache"
    auth_dir.mkdir()

    cache_dir = auth_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "compiled.pyc").write_text("bytecode")

    (auth_dir / "app.py").write_text("code")

    engine = PolicyEngine(authorized_roots=[auth_dir])
    res = search_files(pattern="compiled", root_dir=str(auth_dir), policy_engine=engine)
    assert res.success is True
    assert res.result["count"] == 0  # Should skip __pycache__


def test_dictation_confirmation_and_mock():
    text_en = "Hello from local AI assistant"
    text_fa = "سلام، این یک آزمایش تایپ خودکار است"

    # 1. Unconfirmed English call requires confirmation
    res_unconf = insert_text(text=text_en, confirmed=False, mock_for_test=True)
    assert res_unconf.status == ExecutionStatus.AWAITING_CONFIRMATION
    assert res_unconf.result["action"] == "insert_text"
    assert "Please confirm" in res_unconf.result["confirmation_prompt"]

    # 2. Confirmed English call succeeds
    res_conf_en = insert_text(text=text_en, confirmed=True, mock_for_test=True)
    assert res_conf_en.success is True
    assert res_conf_en.result["status"] == "typed"
    assert res_conf_en.result["length"] == len(text_en)

    # 3. Confirmed Persian call succeeds and preserves Unicode string
    res_conf_fa = insert_text(text=text_fa, confirmed=True, mock_for_test=True)
    assert res_conf_fa.success is True
    assert res_conf_fa.result["status"] == "typed"
    assert res_conf_fa.result["length"] == len(text_fa)
    assert res_conf_fa.result["text"] == text_fa

    # 4. Blank text rejected
    res_blank = insert_text(text="   ", confirmed=True, mock_for_test=True)
    assert res_blank.success is False
