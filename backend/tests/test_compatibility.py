from app.logic.compatibility import check_compatibility, infer_board_socket, infer_cpu_socket


def test_socket_inference_understands_common_amd_platforms():
    assert infer_cpu_socket("AMD Ryzen 5 3600") == "AM4"
    assert infer_cpu_socket("AMD Ryzen 5 7600") == "AM5"
    assert infer_board_socket("MSI B450 TOMAHAWK") == "AM4"
    assert infer_board_socket("ASUS B650 PLUS") == "AM5"


def test_compatibility_rejects_cross_socket_candidate():
    result = check_compatibility({
        "cpu": "AMD Ryzen 5 7600",
        "gpu": None,
        "motherboard": "B450 AM4 DDR4",
        "ram": "DDR4 16GB",
        "psu_watt": None,
        "storage": [],
        "use_case": None,
    })

    assert any("CPU 소켓 AM5" in issue["message"] for issue in result["issues"])


def test_existing_nvme_is_evidence_that_replacement_nvme_is_supported():
    result = check_compatibility({
        "cpu": "AMD Ryzen 7 9800X3D",
        "gpu": None,
        "motherboard": "ASUS TUF GAMING B850-PLUS WIFI",
        "ram": None,
        "psu_watt": None,
        "storage": [{"type": "NVMe", "capacity_gb": 1000}],
        "existing_storage": [{"type": "NVMe"}],
        "use_case": None,
    })

    assert not any(issue["component"] == "Storage / 메인보드" for issue in result["issues"])
