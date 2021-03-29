import os
pjoin = os.path.join
import pytest


@pytest.fixture
def setup_env(tmpdir, monkeypatch):
    monkeypatch.setenv('JUPYTER_CONFIG_DIR', pjoin(tmpdir.dirname, 'jupyter'))
    monkeypatch.setenv('JUPYTER_DATA_DIR', pjoin(tmpdir.dirname, 'jupyter_data'))
    monkeypatch.setenv('JUPYTER_RUNTIME_DIR', pjoin(tmpdir.dirname, 'jupyter_runtime'))
    monkeypatch.setenv('IPYTHONDIR', pjoin(tmpdir.dirname, 'ipython'))
