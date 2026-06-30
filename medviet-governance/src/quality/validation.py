# src/quality/validation.py
# Dùng pandas thuần thay great-expectations để tránh lỗi Windows Long Path
import re
import pandas as pd


def build_patient_expectation_suite() -> dict:
    """
    Validate patient data và trả về kết quả dạng dict (thay great-expectations).
    """
    df = pd.read_csv("data/raw/patients_raw.csv")
    return _run_checks(df, label="raw")


def _run_checks(df: pd.DataFrame, label: str) -> dict:
    results = {"label": label, "passed": [], "failed": []}

    def check(name, condition, msg=""):
        if condition:
            results["passed"].append(name)
        else:
            results["failed"].append(f"{name}: {msg}")

    # 1. patient_id không được null
    check("patient_id_not_null",
          df["patient_id"].notnull().all(),
          "có null values")

    # 2. cccd phải có đúng 12 ký tự
    check("cccd_length_12",
          df["cccd"].astype(str).str.len().eq(12).all(),
          "không phải tất cả đều 12 ký tự")

    # 3. ket_qua_xet_nghiem phải trong khoảng [0, 50]
    check("ket_qua_in_range",
          df["ket_qua_xet_nghiem"].between(0, 50).all(),
          "có giá trị ngoài [0, 50]")

    # 4. benh phải thuộc danh sách hợp lệ
    valid_conditions = {"Tiểu đường", "Huyết áp cao", "Tim mạch", "Khỏe mạnh"}
    check("benh_valid_set",
          df["benh"].isin(valid_conditions).all(),
          f"có giá trị ngoài {valid_conditions}")

    # 5. email phải match regex pattern
    email_regex = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    check("email_format",
          df["email"].astype(str).str.match(email_regex).all(),
          "có email không hợp lệ")

    # 6. Không được có duplicate patient_id
    check("patient_id_unique",
          df["patient_id"].is_unique,
          "có duplicate patient_id")

    results["success"] = len(results["failed"]) == 0
    return results


def validate_anonymized_data(filepath: str) -> dict:
    """
    Validate anonymized data.
    Trả về dict: {"success": bool, "failed_checks": list, "stats": dict}
    """
    df = pd.read_csv(filepath)
    original_df = pd.read_csv("data/raw/patients_raw.csv")

    results = {
        "success": True,
        "failed_checks": [],
        "stats": {
            "total_rows": len(df),
            "columns": list(df.columns)
        }
    }

    # Check 1: Không còn CCCD gốc trong output
    original_cccds = set(original_df["cccd"].astype(str).tolist())
    leaked = [v for v in df["cccd"].astype(str) if v in original_cccds]
    if leaked:
        results["success"] = False
        results["failed_checks"].append(
            f"CCCD gốc vẫn còn trong output: {len(leaked)} records"
        )

    # Check 2: Không có null values trong các cột quan trọng
    for col in ["patient_id", "benh", "ket_qua_xet_nghiem"]:
        if col in df.columns and df[col].isnull().any():
            results["success"] = False
            results["failed_checks"].append(f"Cột '{col}' có null values")

    # Check 3: Số rows phải bằng original
    if len(df) != len(original_df):
        results["success"] = False
        results["failed_checks"].append(
            f"Số rows không khớp: anonymized={len(df)}, original={len(original_df)}"
        )

    return results
