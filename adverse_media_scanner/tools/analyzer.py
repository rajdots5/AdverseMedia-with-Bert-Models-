import json
import warnings
from observability import traced_span
from transformers import pipeline
from config_manager import get_config_list, get_config_int

warnings.filterwarnings("ignore")

print("⏳ Loading local BERT models...")
with traced_span("initialize_local_models", "CHAIN") as span:
    ner_pipeline = pipeline("ner", model="dslim/bert-base-NER", aggregation_strategy="simple")
    classifier_pipeline = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    if span:
        span.set_attribute("model.ner_name", "dslim/bert-base-NER")
        span.set_attribute("model.risk_name", "facebook/bart-large-mnli")
        span.set_attribute("model.ner_device", str(getattr(ner_pipeline, "device", "unknown")))
        span.set_attribute("model.risk_device", str(getattr(classifier_pipeline, "device", "unknown")))
        span.set_attribute("output.value", json.dumps({
            "ner_model": "dslim/bert-base-NER",
            "risk_model": "facebook/bart-large-mnli",
            "ner_device": str(getattr(ner_pipeline, "device", "unknown")),
            "risk_device": str(getattr(classifier_pipeline, "device", "unknown")),
        }))
print("✅ Local BERT models loaded successfully!")


def resolve_entity_with_weights(target_name: str, kyc_profile: dict, article_text: str) -> dict:
    """
    Multi-Factor Weighted Entity Resolution Engine + Financial Context Filter:
    - Name Match Weight: 50%
    - Location / City Weight: 25%
    - Company / Business Association Weight: 25%
    """
    if not article_text:
        return {
            "is_match": False,
            "entity_confidence": 0.0,
            "reasoning": "Empty text",
            "factor_scores": {"name": 0.0, "location": 0.0, "association": 0.0},
            "financial_context": False,
            "matched_association_count": 0,
            "ner_used": False,
            "extracted_names": [],
        }

    text_lower = article_text.lower()
    target_clean = target_name.lower().strip()

    # 🛑 1. FINANCIAL RELEVANCE FILTER (Bank-Grade Check)
    # Agar article me banking, fraud ya financial crime ke indicators nahi hain, toh irrelevant maankar reject karo.
    financial_indicators = [
        'bank', 'fraud', 'money', 'laundering', 'scam', 'loan', 'crore', 
        'lakh', 'rbi', 'ed', 'cbi', 'financial', 'accounts', 'embezzlement', 'pmla', 'default', 'penalty'
    ]
    has_financial_context = any(ind in text_lower for ind in financial_indicators)

    if not has_financial_context:
        return {
            "is_match": False,
            "entity_confidence": 0.0,
            "reasoning": "Filtered out: Article matches name but lacks financial/banking crime context.",
            "factor_scores": {"name": 0.0, "location": 0.0, "association": 0.0},
            "financial_context": False,
            "matched_association_count": 0,
            "ner_used": False,
            "extracted_names": [],
        }

    # 2. Name Match (50% weight)
    name_score = 0.0
    ner_used = False
    extracted_names = []
    if target_clean in text_lower:
        name_score = 0.50
    else:
        ner_used = True
        ner_input = article_text[:1500]
        with traced_span("person_entity_recognition", "CHAIN") as span:
            if span:
                span.set_attribute("input.value", ner_input)
                span.set_attribute("ner.input_characters", len(ner_input))
            entities = ner_pipeline(ner_input)
            extracted_names = [
                ent["word"].replace("##", "").strip().lower()
                for ent in entities if ent.get("entity_group") == "PER"
            ]
            if span:
                span.set_attribute("ner.person_entity_count", len(extracted_names))
                span.set_attribute("output.value", json.dumps({"person_entities": extracted_names}, ensure_ascii=True))
        if any(name in target_clean or target_clean in name for name in extracted_names):
            name_score = 0.30

    # 3. Location Match (25% weight)
    city = kyc_profile.get("city", "").lower().strip()
    location_score = 0.0
    if city and city in text_lower:
        location_score = 0.25

    # 4. Association / Company Match (25% weight)
    companies = [c.strip().lower() for c in kyc_profile.get("associated_companies", "").split(",") if c.strip()]
    company_score = 0.0
    matched_comps = [comp for comp in companies if comp in text_lower]
    if matched_comps:
        company_score = 0.25

    # Total Dynamic Weighted Score
    total_confidence = name_score + location_score + company_score

    # Threshold: Name match hona zaroori hai
    is_match = name_score > 0.0 and total_confidence >= 0.40

    reasoning = (
        f"Financial context verified. Weights -> Name: {name_score*100:.0f}%, "
        f"Location ({kyc_profile.get('city','N/A')}): {location_score*100:.0f}%, "
        f"Associations Found: {matched_comps if matched_comps else 'None'} ({company_score*100:.0f}%). "
        f"Total Match Score: {total_confidence*100:.0f}%."
    )

    return {
        "is_match": is_match,
        "entity_confidence": round(total_confidence, 2),
        "reasoning": reasoning,
        "factor_scores": {
            "name": name_score,
            "location": location_score,
            "association": company_score,
        },
        "financial_context": has_financial_context,
        "matched_association_count": len(matched_comps),
        "ner_used": ner_used,
        "extracted_names": extracted_names,
    }


def classify_risk(article_text: str) -> dict:
    if not article_text:
        return {
            "risk_category": "None",
            "confidence_score": 0.0,
            "chunks_analyzed": 0,
            "fallback_used": False,
            "candidate_labels": [],
            "fallback_keywords": [],
            "chunk_size": 0,
            "max_text_scan_limit": 0,
            "chunk_results": [],
        }

    labels = get_config_list(
        "risk_labels", 
        ["Financial Fraud", "Money Laundering", "Arrest or Extradition", "Legal Penalty or Court Order", "Normal Business News"]
    )
    fallback_keywords = get_config_list(
        "risk_fallback_keywords", 
        ["fraud", "scam", "money laundering", "cbi", "ed raid", "court", "penalty"]
    )
    chunk_size = get_config_int("chunk_size", 1000)
    max_limit = get_config_int("max_text_scan_limit", 4000)

    chunks = [article_text[i:i + chunk_size] for i in range(0, min(len(article_text), max_limit), chunk_size)]

    highest_risk_label = "Normal Business News"
    max_risk_score = 0.0
    fallback_used = False
    chunk_results = []

    for chunk_index, chunk in enumerate(chunks):
        with traced_span("zero_shot_classification_chunk", "CHAIN", {"chunk.index": chunk_index}) as span:
            if span:
                span.set_attribute("input.value", json.dumps({
                    "text": chunk,
                    "candidate_labels": labels,
                }, ensure_ascii=True))
                span.set_attribute("chunk.start_character", chunk_index * chunk_size)
                span.set_attribute("chunk.end_character", min((chunk_index + 1) * chunk_size, max_limit, len(article_text)))

            chunk_lower = chunk.lower()
            classification = classifier_pipeline(chunk, candidate_labels=labels, multi_label=False)
            model_labels = classification["labels"]
            model_scores = [float(score) for score in classification["scores"]]
            top_label = model_labels[0]
            top_score = model_scores[0]
            chunk_fallback_used = False

            if top_label == "Normal Business News" and any(w in chunk_lower for w in fallback_keywords):
                fallback_used = True
                chunk_fallback_used = True
                top_label = "Financial Fraud / Penalty"
                fraud_scores = [
                    score for label, score in zip(model_labels, model_scores)
                    if label != "Normal Business News"
                ]
                dynamic_boost = max(fraud_scores) + 0.30 if fraud_scores else 0.70
                top_score = min(dynamic_boost, 0.98)

            chunk_result = {
                "chunk_index": chunk_index,
                "start_character": chunk_index * chunk_size,
                "end_character": min((chunk_index + 1) * chunk_size, max_limit, len(article_text)),
                "model_labels": model_labels,
                "model_scores": model_scores,
                "selected_category": top_label,
                "selected_confidence": top_score,
                "fallback_used": chunk_fallback_used,
            }
            chunk_results.append(chunk_result)
            if span:
                span.set_attribute("risk.fallback_used", chunk_fallback_used)
                span.set_attribute("output.value", json.dumps(chunk_result, ensure_ascii=True))

            if top_label != "Normal Business News" and top_score > max_risk_score:
                max_risk_score = top_score
                highest_risk_label = top_label

    return {
        "risk_category": highest_risk_label,
        "confidence_score": round(max_risk_score, 2),
        "chunks_analyzed": len(chunks),
        "fallback_used": fallback_used,
        "candidate_labels": labels,
        "fallback_keywords": fallback_keywords,
        "chunk_size": chunk_size,
        "max_text_scan_limit": max_limit,
        "chunk_results": chunk_results,
    }