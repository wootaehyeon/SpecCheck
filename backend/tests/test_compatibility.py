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
