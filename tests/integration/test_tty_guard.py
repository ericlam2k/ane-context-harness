"""TTY guard: update/proxy refuse interactive stdin instead of blocking.

A bare `update`/`proxy` on a terminal would wait on stdin forever, hanging
whatever agent invoked it (the VS Code sidebar queue stall). Fail fast.
"""
import io
import json

from ane_context_harness.cli import main


class _TtyStdin(io.StringIO):
    def isatty(self):
        return True


def test_update_tty_stdin_exits_2(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _TtyStdin(""))
    assert main(["update", "--repo-id", "any", "--budget", "200"]) == 2
    _, err = capsys.readouterr()
    assert json.loads(err)["ok"] is False
    assert "interactive terminal" in err


def test_proxy_tty_stdin_exits_2(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _TtyStdin(""))
    assert main(["proxy", "--repo-id", "any", "--budget", "200"]) == 2
    _, err = capsys.readouterr()
    assert json.loads(err)["ok"] is False
    assert "--tasks-file" in err


def test_piped_stdin_still_works(monkeypatch, capsys, tmp_path):
    class _PipeStdin(io.StringIO):
        def isatty(self):
            return False
    monkeypatch.setattr("sys.stdin", _PipeStdin("hello task\n"))
    rc = main(["proxy", "--repo-id", "tty-pipe-test",
               "--repo", "tests/fixtures/synthetic_py_project",
               "--budget", "200"])
    assert rc == 0
