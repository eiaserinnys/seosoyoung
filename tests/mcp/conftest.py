import pytest


@pytest.fixture
def file_workspace(request, tmp_path, monkeypatch):
    """파일 도구와 시험이 같은 임시 작업 공간을 사용한다."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("seosoyoung.mcp.tools.attach.WORKSPACE_ROOT", str(workspace))
    monkeypatch.setattr("seosoyoung.mcp.tools.slack_messaging.WORKSPACE_ROOT", str(workspace))
    request.instance.workspace = workspace
