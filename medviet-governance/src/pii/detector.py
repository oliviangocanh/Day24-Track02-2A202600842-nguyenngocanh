# src/pii/detector.py
import spacy
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import SpacyNlpEngine


class _ViBlankNlpEngine(SpacyNlpEngine):
    """
    SpaCy NLP engine dùng blank English model cho tokenization.
    Không cần download model nào. Các recognizer regex vẫn hoạt động bình thường.
    """

    def load(self) -> None:
        self.nlp = {"en": spacy.blank("en")}


def build_vietnamese_analyzer() -> AnalyzerEngine:
    """
    Xây dựng AnalyzerEngine với các recognizer tùy chỉnh cho VN.
    Dùng spacy.blank("en") làm NLP engine để tránh phụ thuộc model bên ngoài.
    Tất cả PII detection dựa trên regex — không cần NER.
    """

    nlp_engine = _ViBlankNlpEngine()
    nlp_engine.load()

    # --- TASK 2.2.1 ---
    # CCCD VN: đúng 12 chữ số
    cccd_recognizer = PatternRecognizer(
        supported_entity="VN_CCCD",
        supported_language="en",
        patterns=[Pattern("cccd_pattern", r"\b\d{12}\b", 0.9)],
        context=["cccd", "can cuoc", "chung minh", "cmnd"]
    )

    # --- TASK 2.2.2 ---
    # Số điện thoại VN: 0[35789] + 8 chữ số
    phone_recognizer = PatternRecognizer(
        supported_entity="VN_PHONE",
        supported_language="en",
        patterns=[Pattern("vn_phone", r"\b0[35789]\d{8}\b", 0.85)],
        context=["dien thoai", "sdt", "phone"]
    )

    # --- TASK 2.2.3 ---
    # Tên người VN: 2–4 từ có chữ hoa đầu (bao gồm ký tự Unicode tiếng Việt)
    # Dùng \w (khớp Unicode trong Python 3), yêu cầu chữ in hoa ASCII ở đầu từ đầu tiên
    name_recognizer = PatternRecognizer(
        supported_entity="PERSON",
        supported_language="en",
        patterns=[Pattern(
            "vn_name",
            r"\b[A-ZĐĂƠƯÀ-Ö]\w+(?:\s+\w+){1,3}\b",
            0.65
        )],
    )

    # --- TASK 2.2.4 ---
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    analyzer.registry.add_recognizer(cccd_recognizer)
    analyzer.registry.add_recognizer(phone_recognizer)
    analyzer.registry.add_recognizer(name_recognizer)

    return analyzer


def detect_pii(text: str, analyzer: AnalyzerEngine) -> list:
    """
    Detect PII trong text tiếng Việt.
    Dùng language="en" vì NLP engine được cấu hình với blank English model.
    """
    results = analyzer.analyze(
        text=text,
        language="en",
        entities=["PERSON", "EMAIL_ADDRESS", "VN_CCCD", "VN_PHONE"]
    )
    return results
