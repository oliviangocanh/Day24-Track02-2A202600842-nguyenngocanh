# MedViet Governance — Data Governance & Security Lab

**Sinh viên:** Nguyễn Ngọc Anh — MSSV: 2A202600842  
**Môn học:** AICB-P2T2 · Lab #24  
**Ngày nộp:** 30/06/2026

---

## Tổng quan

Lab xây dựng hệ thống Data Governance cho AI Platform của startup y tế **MedViet**, gồm:

- **PII Detection & Anonymization** — phát hiện và ẩn danh hóa thông tin cá nhân trong dữ liệu bệnh nhân
- **RBAC** — kiểm soát truy cập theo vai trò (Casbin)
- **ABAC / OPA** — policy-based access control bằng Rego
- **Envelope Encryption** — mã hóa dữ liệu AES-256-GCM
- **REST API** — FastAPI với auth middleware
- **Compliance** — mapping NĐ13/2023 và ISO 27001

**Kết quả test: 6/6 PASSED ✅**

---

## Cài đặt môi trường

Virtual environment đặt ở thư mục này (cùng cấp với `medviet-governance/`):

```bash
# Tạo venv (nếu chưa có)
python -m venv venv

# Kích hoạt — Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Kích hoạt — Linux/macOS:
source venv/bin/activate

# Cài thư viện
cd medviet-governance
pip install -r requirements.txt
```

> **Không cần download spaCy model** — project dùng `spacy.blank("en")` thay thế `vi_core_news_lg` để tránh lỗi tương thích spaCy 3.8.

---

## Chạy dự án

Tất cả lệnh bên dưới chạy từ thư mục `medviet-governance/`.

### 1. Sinh dữ liệu giả

```bash
python scripts/generate_data.py
```

Tạo `data/raw/patients_raw.csv` — 200 bản ghi bệnh nhân giả (họ tên, CCCD, SĐT, email, địa chỉ, chẩn đoán, kết quả xét nghiệm).

### 2. Chạy test suite

```bash
pytest tests/test_pii.py -v
```

Kết quả mong đợi:

```
tests/test_pii.py::TestPIIDetection::test_cccd_detected                    PASSED
tests/test_pii.py::TestPIIDetection::test_phone_detected                   PASSED
tests/test_pii.py::TestPIIDetection::test_email_detected                   PASSED
tests/test_pii.py::TestPIIDetection::test_detection_rate_above_95_percent  PASSED
tests/test_pii.py::TestAnonymization::test_pii_not_in_output               PASSED
tests/test_pii.py::TestAnonymization::test_non_pii_columns_unchanged       PASSED

6 passed in ~5s
```

### 3. Khởi động API

```bash
uvicorn src.api.main:app --reload
```

API chạy tại `http://localhost:8000`.

**Test nhanh bằng curl:**

```bash
# Health check
curl http://localhost:8000/health

# Admin đọc raw data (200)
curl -H "Authorization: Bearer token-alice" http://localhost:8000/api/patients/raw

# ML Engineer đọc anonymized data (200)
curl -H "Authorization: Bearer token-bob" http://localhost:8000/api/patients/anonymized

# ML Engineer đọc raw data → BỊ TỪ CHỐI (403)
curl -H "Authorization: Bearer token-bob" http://localhost:8000/api/patients/raw

# Data Analyst xem thống kê (200)
curl -H "Authorization: Bearer token-carol" http://localhost:8000/api/metrics/aggregated

# Intern xóa bệnh nhân → BỊ TỪ CHỐI (403)
curl -X DELETE -H "Authorization: Bearer token-dave" \
  http://localhost:8000/api/patients/<patient_id>
```

**Token thử nghiệm:**

| Token | User | Role |
|-------|------|------|
| `token-alice` | alice | admin |
| `token-bob` | bob | ml_engineer |
| `token-carol` | carol | data_analyst |
| `token-dave` | dave | intern |

### 4. Quét bảo mật (tuỳ chọn)

```bash
bandit -r src/
pip-audit
```

---

## Cấu trúc thư mục

```
medviet-governance/
├── data/
│   └── raw/
│       └── patients_raw.csv          # Sinh bởi generate_data.py
├── policies/
│   └── opa_policy.rego               # ABAC policies (OPA/Rego)
├── scripts/
│   └── generate_data.py              # Tạo 200 bản ghi giả
├── src/
│   ├── access/
│   │   ├── model.conf                # Casbin RBAC model
│   │   ├── policy.csv                # Role → resource → action
│   │   └── rbac.py                   # get_current_user, require_permission
│   ├── api/
│   │   └── main.py                   # FastAPI endpoints
│   ├── encryption/
│   │   └── vault.py                  # Envelope encryption AES-256-GCM
│   ├── pii/
│   │   ├── detector.py               # build_vietnamese_analyzer, detect_pii
│   │   └── anonymizer.py             # MedVietAnonymizer (replace/mask/hash)
│   └── quality/
│       └── validation.py             # Data quality checks (pandas)
├── tests/
│   └── test_pii.py                   # 6 test cases
├── compliance_checklist.md           # NĐ13/2023 compliance
├── report.md                         # Báo cáo chi tiết
└── requirements.txt
```

---

## Tóm tắt những gì đã triển khai

### Module 1 — PII Detection (`src/pii/detector.py`)

Dùng Microsoft Presidio với NLP engine tùy chỉnh để tránh lỗi tương thích spaCy 3.8:

```python
class _ViBlankNlpEngine(SpacyNlpEngine):
    def load(self):
        self.nlp = {"en": spacy.blank("en")}  # không cần vi_core_news_lg
```

4 loại PII được detect bằng regex:

| Entity | Pattern |
|--------|---------|
| `VN_CCCD` | `\b\d{12}\b` |
| `VN_PHONE` | `\b0[35789]\d{8}\b` |
| `PERSON` | Regex Unicode tên tiếng Việt |
| `EMAIL_ADDRESS` | Presidio built-in |

### Module 2 — Anonymization (`src/pii/anonymizer.py`)

3 chiến lược ẩn danh: `replace` (Faker), `mask` (`****`), `hash` (SHA-256).

`anonymize_dataframe()` xử lý từng cột theo mục đích:
- `ho_ten`, `dia_chi`, `email` → qua Presidio anonymizer
- `cccd`, `so_dien_thoai` → thay trực tiếp bằng fake data
- `benh`, `ket_qua_xet_nghiem`, `patient_id` → **giữ nguyên** (cần cho ML)

**Detection rate: 100%** (yêu cầu ≥ 95%).

> **Bug đã fix:** Pandas tự drop leading zero khi đọc CSV (`"0912345678"` → `912345678`). Fix: dùng `zfill(10)` / `zfill(12)` trước khi đưa vào regex.

### Module 3 — RBAC (`src/access/rbac.py`)

Casbin enforcer đọc policy từ `policy.csv`, model từ `model.conf`.

- **HTTP 401** nếu thiếu hoặc sai Bearer token
- **HTTP 403** nếu role không có quyền trên resource

### Module 4 — OPA Policy (`policies/opa_policy.rego`)

ABAC bổ sung cho RBAC — xử lý các quy tắc phức tạp:
- ML Engineer không được xóa production data
- Không ai được export `restricted` data ra ngoài server VN

### Module 5 — Envelope Encryption (`src/encryption/vault.py`)

```
KEK (256-bit) ──encrypts──► DEK (256-bit, mới mỗi record)
                                      │
                              encrypts▼
                           Plaintext data (AES-256-GCM, nonce 96-bit)
```

DEK bị xóa khỏi memory ngay sau khi encrypt (`del plaintext_dek`).

### Module 6 — Data Quality (`src/quality/validation.py`)

6 validation checks bằng pandas (thay `great-expectations` — gây lỗi Windows Long Path):
`patient_id` không null, CCCD 12 ký tự, kết quả trong [0,50], bệnh hợp lệ, email đúng format, patient_id không trùng.

### Module 7 — REST API (`src/api/main.py`)

| Endpoint | Method | Role tối thiểu |
|----------|--------|---------------|
| `/api/patients/raw` | GET | admin |
| `/api/patients/anonymized` | GET | ml_engineer |
| `/api/metrics/aggregated` | GET | data_analyst |
| `/api/patients/{id}` | DELETE | admin |
| `/health` | GET | — |

---

## Mapping NĐ13/2023

| Yêu cầu | Giải pháp | Trạng thái |
|---------|----------|-----------|
| Tối thiểu hóa dữ liệu | PII anonymization (Presidio) | ✅ |
| Kiểm soát truy cập | RBAC (Casbin) + ABAC (OPA) | ✅ |
| Mã hóa | AES-256-GCM envelope encryption | ✅ |
| Quyền xóa dữ liệu | `DELETE /api/patients/{id}` | ✅ |
| Lưu trữ trong nước | OPA data locality policy | ✅ |
| Ghi nhật ký kiểm toán | FastAPI audit middleware | ✅ |
| Phát hiện vi phạm 72h | Prometheus + Grafana alerting | ✅ |
| DPO | dpo@medviet.vn | ✅ |
