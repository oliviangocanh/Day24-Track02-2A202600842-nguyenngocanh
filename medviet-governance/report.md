# Báo cáo Lab: Data Governance & Security — MedViet AI Platform

**Sinh viên:** Nguyễn Ngọc Anh (2A202600842)  
**Ngày nộp:** 30/06/2026  
**Track:** 02 — AI Platform Governance

---

## 1. Tổng quan

MedViet là startup y tế đang xây dựng nền tảng AI để phân tích dữ liệu bệnh nhân. Lab này yêu cầu thiết kế và triển khai hệ thống Data Governance đáp ứng **Nghị định 13/2023/NĐ-CP** (bảo vệ dữ liệu cá nhân Việt Nam) và chuẩn **ISO 27001**.

**Kết quả test cuối cùng:** 6/6 passed ✅

```
tests/test_pii.py::TestPIIDetection::test_cccd_detected              PASSED
tests/test_pii.py::TestPIIDetection::test_phone_detected             PASSED
tests/test_pii.py::TestPIIDetection::test_email_detected             PASSED
tests/test_pii.py::TestPIIDetection::test_detection_rate_above_95_percent PASSED
tests/test_pii.py::TestAnonymization::test_pii_not_in_output         PASSED
tests/test_pii.py::TestAnonymization::test_non_pii_columns_unchanged PASSED
```

---

## 2. Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI REST API                         │
│   /api/patients/raw  /api/patients/anonymized               │
│   /api/metrics/aggregated  /api/patients/{id} (DELETE)      │
└───────────────┬───────────────┬─────────────────────────────┘
                │               │
        ┌───────▼──────┐ ┌─────▼────────┐
        │  RBAC (Casbin)│ │ PII Pipeline │
        │  + OPA/Rego   │ │  Presidio    │
        └───────────────┘ └──────────────┘
                                │
                    ┌───────────▼──────────┐
                    │  Envelope Encryption │
                    │  AES-256-GCM (Vault) │
                    └──────────────────────┘
```

**Dữ liệu đầu vào:** 200 bản ghi bệnh nhân giả (Faker `vi_VN`) gồm: `patient_id`, `ho_ten`, `cccd`, `ngay_sinh`, `so_dien_thoai`, `email`, `dia_chi`, `benh`, `ket_qua_xet_nghiem`, `bac_si_phu_trach`, `ngay_kham`.

---

## 3. Module triển khai

### 3.1 PII Detection (`src/pii/detector.py`)

**Thách thức:** `vi_core_news_lg` (mô hình NLP tiếng Việt) không tương thích với spaCy 3.8.x. Giải pháp: dùng `spacy.blank("en")` làm tokenizer backbone — toàn bộ detection vẫn hoạt động vì chỉ dựa trên regex, không cần NER.

| Entity | Pattern | Confidence |
|--------|---------|-----------|
| `VN_CCCD` | `\b\d{12}\b` | 0.90 |
| `VN_PHONE` | `\b0[35789]\d{8}\b` | 0.85 |
| `PERSON` | `\b[A-ZĐĂƠƯÀ-Ö]\w+(?:\s+\w+){1,3}\b` | 0.65 |
| `EMAIL_ADDRESS` | Built-in Presidio recognizer | — |

```python
class _ViBlankNlpEngine(SpacyNlpEngine):
    def load(self) -> None:
        self.nlp = {"en": spacy.blank("en")}  # bypass vi_core_news_lg

analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
```

### 3.2 PII Anonymization (`src/pii/anonymizer.py`)

Ba chiến lược được hỗ trợ:

| Strategy | Mô tả | Ví dụ |
|----------|-------|-------|
| `replace` | Thay bằng fake data (Faker) | `Nguyễn Văn A` → `Trần Thị B` |
| `mask` | Che ký tự bằng `*` | `012345678901` → `0123****8901` |
| `hash` | SHA-256 one-way hash | `test@gmail.com` → `a94f2b3c...` |

`anonymize_dataframe()` xử lý từng cột khác nhau:
- `ho_ten`, `dia_chi`, `email` — qua `anonymize_text()` (Presidio)
- `cccd`, `so_dien_thoai` — thay trực tiếp bằng fake data (tránh phụ thuộc detection)
- `bac_si_phu_trach` — thay bằng tên giả
- `benh`, `ket_qua_xet_nghiem`, `patient_id` — **giữ nguyên**

**Detection rate đạt 100%** (≥ yêu cầu 95%). Lưu ý kỹ thuật: pandas tự convert cột số sang `int` khi đọc CSV, làm mất leading zero (`"0912345678"` → `912345678`). Fix: `zfill(10)` cho phone, `zfill(12)` cho CCCD trước khi analyze.

### 3.3 RBAC với Casbin (`src/access/rbac.py`)

Mô hình **Role-Based Access Control** dùng thư viện Casbin (policy file `policy.csv`, model file `model.conf`).

| Role | Quyền |
|------|-------|
| `admin` | Đọc/ghi/xóa `patient_data`, đọc/ghi `model_artifacts` |
| `ml_engineer` | Đọc/ghi `training_data`, `model_artifacts` |
| `data_analyst` | Đọc `aggregated_metrics`, ghi `reports` |
| `intern` | Đọc/ghi `sandbox_data` |

```python
# HTTP 401 nếu thiếu/sai Bearer token
# HTTP 403 nếu role không đủ quyền
allowed = enforcer.enforce(role, resource, action)
if not allowed:
    raise HTTPException(status_code=403, ...)
```

### 3.4 OPA Policy (`policies/opa_policy.rego`)

**Attribute-Based Access Control** bổ sung cho RBAC, viết bằng Rego:

```rego
package medviet.data_access

default allow := false

allow if { input.user.role == "admin" }

allow if {
    input.user.role == "ml_engineer"
    input.resource in {"training_data", "model_artifacts"}
    input.action in {"read", "write"}
}

# Không ai được export restricted data ra ngoài VN servers
deny if {
    input.data_classification == "restricted"
    input.destination_country != "VN"
}
```

OPA xử lý các quy tắc phức tạp hơn (data locality, attribute-based conditions) mà RBAC thuần không mô tả được.

### 3.5 Envelope Encryption (`src/encryption/vault.py`)

Kiến trúc **KEK → DEK → Data** (mô phỏng AWS KMS cho local dev):

```
Master Key (KEK, 256-bit)
    └── encrypts → Data Key (DEK, 256-bit, mới cho mỗi record)
                       └── encrypts → Plaintext data
                                         (AES-256-GCM, nonce 96-bit)
```

- KEK lưu tại `.vault_key` (production: HSM/KMS)
- DEK được xóa khỏi memory ngay sau khi encrypt (`del plaintext_dek`)
- Output: `{"encrypted_dek": "...", "ciphertext": "...", "algorithm": "AES-256-GCM"}`

### 3.6 Data Quality (`src/quality/validation.py`)

Validation thuần pandas (thay `great-expectations` — gây lỗi Windows Long Path do kéo theo JupyterLab):

| Check | Điều kiện |
|-------|----------|
| `patient_id_not_null` | Không có null |
| `cccd_length_12` | Đúng 12 ký tự |
| `ket_qua_in_range` | Trong khoảng [0, 50] |
| `benh_valid_set` | Thuộc `{Tiểu đường, Huyết áp cao, Tim mạch, Khỏe mạnh}` |
| `email_format` | Khớp regex email |
| `patient_id_unique` | Không có duplicate |

### 3.7 REST API (`src/api/main.py`)

| Endpoint | Method | Role yêu cầu | Mô tả |
|----------|--------|-------------|-------|
| `/api/patients/raw` | GET | admin | Raw PII data |
| `/api/patients/anonymized` | GET | admin, ml_engineer | Anonymized data |
| `/api/metrics/aggregated` | GET | admin, ml_engineer, data_analyst | Thống kê tổng hợp |
| `/api/patients/{id}` | DELETE | admin | Xóa bệnh nhân (Right to Erasure) |
| `/health` | GET | — | Health check |

---

## 4. Vấn đề gặp phải và giải pháp

| # | Vấn đề | Nguyên nhân | Giải pháp |
|---|--------|------------|-----------|
| 1 | `vi_core_news_lg` không tương thích | spaCy 3.8.x chưa hỗ trợ | Dùng `spacy.blank("en")` làm tokenizer, giữ regex recognizer |
| 2 | `PatternRecognizer` không detect | `supported_language="en"` vs `analyze(language="vi")` | Đồng nhất toàn bộ sang `"en"` |
| 3 | `great-expectations` lỗi Windows Long Path | Path JupyterLab vượt 260 ký tự | Loại bỏ, viết validation thuần pandas |
| 4 | Detection rate 72% (< 95%) | Pandas drop leading zero của CCCD/phone khi đọc CSV | `zfill(12)` cho CCCD, `zfill(10)` cho phone trước khi analyze |

---

## 5. Mapping NĐ13/2023

| Điều khoản NĐ13 | Triển khai kỹ thuật | Trạng thái |
|----------------|-------------------|-----------|
| Tối thiểu hóa dữ liệu | PII anonymization (Presidio) | ✅ |
| Kiểm soát truy cập | RBAC (Casbin) + ABAC (OPA) | ✅ |
| Mã hóa dữ liệu | AES-256-GCM envelope encryption | ✅ |
| Ghi nhật ký kiểm toán | FastAPI audit middleware | ✅ (thiết kế) |
| Phát hiện vi phạm (72h) | Prometheus + Grafana alerting | ✅ (thiết kế) |
| Quyền xóa dữ liệu | `DELETE /api/patients/{id}` | ✅ |
| Lưu trữ trong nước | Data localization policy (OPA) | ✅ |
| Bổ nhiệm DPO | `dpo@medviet.vn` | ✅ |

---

## 6. Kết luận

Hệ thống Data Governance cho MedViet AI Platform đã được triển khai đầy đủ các thành phần theo yêu cầu:

- **PII detection** đạt 100% trên tập dữ liệu 50 bệnh nhân (yêu cầu ≥ 95%)
- **Anonymization** đảm bảo không rò rỉ PII gốc ra output
- **RBAC** enforce đúng quyền theo từng role, trả về 401/403 khi vi phạm
- **Encryption** theo chuẩn AES-256-GCM với envelope pattern (KEK/DEK)
- **OPA policies** bổ sung ABAC cho các quy tắc phức tạp (data locality)
- **Compliance** mapping đầy đủ với NĐ13/2023
