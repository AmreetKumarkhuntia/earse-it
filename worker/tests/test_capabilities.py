from types import SimpleNamespace
from unittest.mock import patch

from erase_it.models import capabilities


def runtime(cuda=None, available=False):
    return SimpleNamespace(version=SimpleNamespace(cuda=cuda), cuda=SimpleNamespace(
        is_available=lambda: available, get_device_name=lambda _: "NVIDIA test GPU"))


def inspect(torch):
    with patch("erase_it.models.importlib.util.find_spec", return_value=object()), patch.dict("sys.modules", torch=torch):
        return capabilities()


def test_cpu_build_explains_missing_cuda_runtime():
    result = inspect(runtime())
    assert result["gpu_status"] == "cpu_only"
    assert result["inference_ready"] and result["cpu_available"]
    assert not result["cuda_available"] and result["cuda_runtime"] is None


def test_cuda_build_without_usable_gpu_is_distinct_from_cpu_build():
    result = inspect(runtime("12.8"))
    assert result["gpu_status"] == "cuda_unavailable"
    assert result["cuda_runtime"] == "12.8"
    assert result["cpu_available"] and not result["cuda_available"]


def test_usable_cuda_device_is_named():
    result = inspect(runtime("12.8", True))
    assert result["gpu_status"] == "available"
    assert result["cuda_available"] and result["cuda_device"] == "NVIDIA test GPU"


def test_missing_or_broken_runtime_keeps_hello_usable():
    with patch("erase_it.models.importlib.util.find_spec", return_value=None):
        result = capabilities()
    assert result["gpu_status"] == "runtime_missing"
    assert not result["inference_ready"]
    result = inspect(None)  # Import fails, for example due to a missing DLL.
    assert result["gpu_status"] == "runtime_error"
    assert result["runtime_error"]
    assert not result["cpu_available"]
