from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from what import cuda_runtime as runtime


@pytest.fixture
def gpu_host(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setattr(runtime.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(runtime.sys, "base_prefix", "/system-python")
    monkeypatch.setattr("what.gpu.detect_gpu", lambda: SimpleNamespace(available=True, device="cuda"))
    monkeypatch.setattr("importlib.metadata.version", lambda _: "4.8.2")
    monkeypatch.setattr(runtime, "library_environment", lambda env: {**env, "LD_LIBRARY_PATH": "/runtime/lib"})


@pytest.mark.parametrize("platform,device", [("darwin", None), ("linux", "cpu")])
def test_skips_macos_and_explicit_cpu(monkeypatch, platform, device):
    monkeypatch.setattr(runtime.sys, "platform", platform)
    detect = Mock(side_effect=AssertionError("must not probe or install"))
    monkeypatch.setattr("what.gpu.detect_gpu", detect)
    assert runtime.prepare_cuda_environment({"KEEP": "yes"}, device=device) == {"KEEP": "yes"}


def test_skips_host_without_gpu(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setattr("what.gpu.detect_gpu", lambda: SimpleNamespace(available=False, device="cpu"))
    assert runtime.prepare_cuda_environment({}) == {}


def test_existing_libraries_require_no_install(gpu_host, monkeypatch):
    monkeypatch.setattr(runtime, "libraries_load", lambda env: True)
    install = Mock(side_effect=AssertionError("must not install"))
    monkeypatch.setattr(runtime.subprocess, "run", install)
    assert runtime.prepare_cuda_environment({})["LD_LIBRARY_PATH"] == "/runtime/lib"


def test_missing_libraries_install_in_current_venv(gpu_host, monkeypatch):
    monkeypatch.setattr(runtime, "libraries_load", Mock(side_effect=[False, False, True]))
    install = Mock()
    monkeypatch.setattr(runtime.subprocess, "run", install)
    assert runtime.prepare_cuda_environment({})["LD_LIBRARY_PATH"] == "/runtime/lib"
    command = install.call_args.args[0]
    assert command[:4] == [runtime.sys.executable, "-m", "pip", "install"]
    assert command[-2:] == list(runtime.CUDA_PACKAGES)
    assert install.call_args.kwargs["check"] is True


def test_failed_install_reports_error_without_prompt(gpu_host, monkeypatch, capsys):
    monkeypatch.setattr(runtime, "libraries_load", lambda env: False)
    monkeypatch.setattr(runtime.subprocess, "run", Mock(side_effect=OSError("offline")))
    runtime.prepare_cuda_environment({})
    assert "setup failed: offline" in capsys.readouterr().err


def test_opt_out_does_not_install(gpu_host, monkeypatch):
    monkeypatch.setattr(runtime, "libraries_load", lambda env: False)
    monkeypatch.setattr(runtime.subprocess, "run", Mock(side_effect=AssertionError("must not install")))
    runtime.prepare_cuda_environment({"WHAT_AUTO_INSTALL_CUDA": "0"})


def test_library_path_preserves_user_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    lib = tmp_path / "nvidia" / "cublas" / "lib"
    lib.mkdir(parents=True)
    monkeypatch.setattr(runtime.sysconfig, "get_path", lambda _: str(tmp_path))
    env = runtime.library_environment({"LD_LIBRARY_PATH": "/custom/lib", "KEEP": "yes"})
    assert env == {"LD_LIBRARY_PATH": f"{lib}:/custom/lib", "KEEP": "yes"}


def test_service_reexecs_once_for_loader_path(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setattr(runtime, "prepare_cuda_environment", lambda **kw: {"LD_LIBRARY_PATH": "/runtime/lib"})
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    monkeypatch.setattr(runtime.sys, "orig_argv", ["python", "-m", "what", "service"])
    execute = Mock()
    monkeypatch.setattr(runtime.os, "execve", execute)
    runtime.prepare_service_runtime()
    assert execute.call_args.args[1] == [runtime.sys.executable, "-m", "what", "service"]
    execute.reset_mock()
    monkeypatch.setenv("LD_LIBRARY_PATH", "/runtime/lib")
    runtime.prepare_service_runtime()
    execute.assert_not_called()


def test_windows_library_path_uses_wheel_bin_dirs_on_path(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    dll_dir = tmp_path / "nvidia" / "cudnn" / "bin"
    dll_dir.mkdir(parents=True)
    monkeypatch.setattr(runtime.sysconfig, "get_path", lambda _: str(tmp_path))
    env = runtime.library_environment({"PATH": "C:/Windows;C:/tools"})
    assert env == {"PATH": f"{dll_dir};C:/Windows;C:/tools"}


def test_windows_missing_libraries_install(gpu_host, monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime, "libraries_load", Mock(side_effect=[False, False, True]))
    install = Mock()
    monkeypatch.setattr(runtime.subprocess, "run", install)
    runtime.prepare_cuda_environment({})
    assert install.call_args.args[0][-2:] == list(runtime.CUDA_PACKAGES)


def test_windows_service_updates_path_in_process(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime, "prepare_cuda_environment", lambda **kw: {"PATH": "C:/nvidia/bin;C:/Windows"})
    execute = Mock(side_effect=AssertionError("Windows must not re-exec"))
    monkeypatch.setattr(runtime.os, "execve", execute)
    monkeypatch.setenv("PATH", "C:/Windows")
    runtime.prepare_service_runtime()
    assert runtime.os.environ["PATH"].startswith("C:/nvidia/bin")


def test_install_target_skips_venv_requirement_and_uses_pip_target(gpu_host, monkeypatch, tmp_path):
    # Packaged apps: bundled Python is not a venv (sys.prefix == base_prefix) but has a
    # writable WHAT_CUDA_TARGET, so installation proceeds into that directory.
    monkeypatch.setattr(runtime.sys, "base_prefix", runtime.sys.prefix)
    monkeypatch.setattr(runtime, "libraries_load", Mock(side_effect=[False, False, True]))
    install = Mock()
    monkeypatch.setattr(runtime.subprocess, "run", install)
    target = tmp_path / "cuda"
    runtime.prepare_cuda_environment({"WHAT_CUDA_TARGET": str(target)})
    command = install.call_args.args[0]
    assert command[command.index("--target") + 1] == str(target)
    assert (target / ".what-cuda-install.lock").exists()


def test_library_path_includes_install_target(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setattr(runtime.sysconfig, "get_path", lambda _: str(tmp_path / "site"))
    lib = tmp_path / "cuda" / "nvidia" / "cudnn" / "lib"
    lib.mkdir(parents=True)
    env = runtime.library_environment({"WHAT_CUDA_TARGET": str(tmp_path / "cuda")})
    assert env["LD_LIBRARY_PATH"] == str(lib)
