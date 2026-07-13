"""ch09 项目指令加载测试。"""

from __future__ import annotations

from cowcode.instructions import Loader


def test_loader_priority_and_missing_files(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    root = tmp_path / "project"
    root.mkdir()
    (root / ".cowcode").mkdir()
    (home / ".cowcode").mkdir(parents=True)
    (root / "COWCODE.md").write_text("root", encoding="utf-8")
    (root / ".cowcode" / "COWCODE.md").write_text("project config", encoding="utf-8")
    (home / ".cowcode" / "COWCODE.md").write_text("user", encoding="utf-8")

    assert Loader(str(root), str(home)).load() == "root\n\nproject config\n\nuser"


def test_include_expands_nested(tmp_path) -> None:
    root = tmp_path / "project"
    rules = root / "rules"
    rules.mkdir(parents=True)
    (root / "COWCODE.md").write_text("A\n@include rules/b.md", encoding="utf-8")
    (rules / "b.md").write_text("B\n@include c.md", encoding="utf-8")
    (rules / "c.md").write_text("C", encoding="utf-8")

    assert Loader(str(root), str(tmp_path / "home")).load() == "A\nB\nC"


def test_include_depth_cycle_escape_and_binary(tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    chain = root
    (root / "COWCODE.md").write_text("@include a.md", encoding="utf-8")
    for name, next_name in [
        ("a.md", "b.md"),
        ("b.md", "c.md"),
        ("c.md", "d.md"),
        ("d.md", "e.md"),
        ("e.md", "f.md"),
    ]:
        (chain / name).write_text(f"@include {next_name}", encoding="utf-8")
    (chain / "f.md").write_text("too deep", encoding="utf-8")
    assert "超过最大嵌套深度" in Loader(str(root), str(tmp_path / "home")).load()

    (root / "COWCODE.md").write_text("@include loop-a.md", encoding="utf-8")
    (root / "loop-a.md").write_text("@include loop-b.md", encoding="utf-8")
    (root / "loop-b.md").write_text("@include loop-a.md", encoding="utf-8")
    assert "检测到环路" in Loader(str(root), str(tmp_path / "home")).load()

    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    (root / "COWCODE.md").write_text("@include ../outside.md", encoding="utf-8")
    assert "路径超出允许范围" in Loader(str(root), str(tmp_path / "home")).load()

    (root / "bin.md").write_bytes(b"a\x00b")
    (root / "COWCODE.md").write_text("@include bin.md", encoding="utf-8")
    assert "二进制文件" in Loader(str(root), str(tmp_path / "home")).load()
