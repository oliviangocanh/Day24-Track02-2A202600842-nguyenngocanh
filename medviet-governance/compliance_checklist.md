# NĐ13/2023 Compliance Checklist — MedViet AI Platform

## A. Data Localization
- [x] Tất cả patient data lưu trên servers đặt tại Việt Nam
- [x] Backup cũng phải ở trong lãnh thổ VN
- [x] Log việc transfer data ra ngoài nếu có

## B. Explicit Consent
- [x] Thu thập consent trước khi dùng data cho AI training
- [x] Có mechanism để user rút consent (Right to Erasure — endpoint DELETE /api/patients/{id})
- [x] Lưu consent record với timestamp

## C. Breach Notification (72h)
- [x] Có incident response plan
- [x] Alert tự động khi phát hiện breach (Prometheus + Grafana alerting)
- [x] Quy trình báo cáo đến cơ quan có thẩm quyền trong 72h

## D. DPO Appointment
- [x] Đã bổ nhiệm Data Protection Officer
- [x] DPO có thể liên hệ tại: dpo@medviet.vn

## E. Technical Controls (mapping từ requirements)
| NĐ13 Requirement | Technical Control | Status | Owner |
|-----------------|-------------------|--------|-------|
| Data minimization | PII anonymization pipeline (Presidio) | ✅ Done | AI Team |
| Access control | RBAC (Casbin) + ABAC (OPA) | ✅ Done | Platform Team |
| Encryption | AES-256-GCM at rest (SimpleVault envelope encryption), TLS 1.3 in transit | ✅ Done | Infra Team |
| Audit logging | FastAPI audit middleware + structured JSON logs | ✅ Done | Platform Team |
| Breach detection | Prometheus metrics + Grafana alert rules | ✅ Done | Security Team |

## F. Giải pháp kỹ thuật cho các mục đã implement

### Audit Logging
Implement FastAPI middleware ghi lại mọi request vào structured JSON log, gửi về hệ thống SIEM. Mỗi log entry bao gồm: timestamp, user, endpoint, HTTP method, IP address, response code.

```python
@app.middleware("http")
async def audit_log_middleware(request: Request, call_next):
    response = await call_next(request)
    logger.info({
        "timestamp": datetime.utcnow().isoformat(),
        "user": request.headers.get("Authorization", "anonymous"),
        "path": request.url.path,
        "method": request.method,
        "status_code": response.status_code,
        "client_ip": request.client.host,
    })
    return response
```

### Breach Detection (Prometheus + Grafana)
- Deploy Prometheus scrape metrics từ FastAPI (`/metrics` endpoint dùng `prometheus-fastapi-instrumentator`)
- Cấu hình Grafana alert khi:
  - Số lượng HTTP 401/403 đột biến trong 5 phút (dấu hiệu brute-force)
  - Số requests vượt ngưỡng bất thường (dấu hiệu data exfiltration)
  - Response time tăng đột biến (dấu hiệu DoS)
- Khi alert kích hoạt → gửi notification qua email đến DPO → trigger incident response trong 72 giờ theo NĐ13/2023
