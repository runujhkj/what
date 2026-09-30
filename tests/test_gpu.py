from what.gpu import detect_gpu, GpuInfo


def test_detect_gpu_returns_info():
    info = detect_gpu()
    assert isinstance(info, GpuInfo)
    assert isinstance(info.available, bool)
    assert isinstance(info.device, str)
    assert isinstance(info.device_count, int)
    assert isinstance(info.backend, str)
    assert isinstance(info.reason, str)
