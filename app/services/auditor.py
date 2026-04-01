import json
import re
from collections import Counter
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AI Visibility Auditor MVP)"
}

STOP_ENTITIES = {
    "The", "This", "That", "These", "Those", "And", "But", "For", "With",
    "From", "About", "Home", "Contact", "Privacy", "Terms", "Cookies",
    "Login", "Sign", "Menu", "Read", "More", "Learn", "Cookie", "Policy",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"
}


# -----------------------------
# Fetching / parsing
# -----------------------------
def fetch_page(url: str, timeout: int = 15):
    response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    return response


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return ""


def extract_visible_text(soup: BeautifulSoup) -> str:
    soup = BeautifulSoup(str(soup), "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def extract_meta_content(soup: BeautifulSoup, name: str = None, prop: str = None) -> str:
    tag = None
    if name:
        tag = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
    if not tag and prop:
        tag = soup.find("meta", attrs={"property": re.compile(f"^{re.escape(prop)}$", re.I)})
    return tag.get("content", "").strip() if tag else ""


def extract_canonical(soup: BeautifulSoup) -> str:
    tag = soup.find(
        "link",
        rel=lambda x: x and "canonical" in [r.lower() for r in (x if isinstance(x, list) else [x])]
    )
    return tag.get("href", "").strip() if tag else ""


def detect_structured_data(soup: BeautifulSoup):
    schema_types = []

    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            items = parsed if isinstance(parsed, list) else [parsed]

            for item in items:
                if isinstance(item, dict):
                    item_type = item.get("@type")
                    if isinstance(item_type, list):
                        schema_types.extend(str(x) for x in item_type)
                    elif item_type:
                        schema_types.append(str(item_type))
        except Exception:
            continue

    if soup.find(attrs={"itemscope": True}) or soup.find(attrs={"itemtype": True}):
        schema_types.append("Microdata")

    cleaned = []
    seen = set()
    for item in schema_types:
        if item not in seen:
            seen.add(item)
            cleaned.append(item)

    return {
        "present": len(cleaned) > 0,
        "types": cleaned
    }


def count_links(soup: BeautifulSoup, base_url: str):
    base_domain = get_domain(base_url)
    internal = 0
    external = 0

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()

        if not href or low.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        if href.startswith("/"):
            internal += 1
            continue

        parsed_domain = get_domain(href)
        if parsed_domain and parsed_domain == base_domain:
            internal += 1
        elif parsed_domain:
            external += 1

    return internal, external


# -----------------------------
# Content / entity helpers
# -----------------------------
def split_sentences(text: str):
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def get_avg_sentence_length(text: str) -> float:
    sentences = split_sentences(text)
    if not sentences:
        return 0.0
    return sum(len(s.split()) for s in sentences) / len(sentences)


def extract_entities_simple(text: str, title: str = "", h1: str = "") -> list[str]:
    candidates = re.findall(
        r"\b(?:[A-Z][a-zA-Z0-9&'-]{2,})(?:\s+[A-Z][a-zA-Z0-9&'-]{2,}){0,2}\b",
        text
    )

    freq = Counter()
    context = f"{title} {h1}".lower()

    for candidate in candidates:
        candidate = candidate.strip()

        parts = candidate.split()
        if candidate in STOP_ENTITIES:
            continue
        if all(part in STOP_ENTITIES for part in parts):
            continue

        freq[candidate] += 1

        if candidate.lower() in context:
            freq[candidate] += 2

    filtered = [(entity, count) for entity, count in freq.items() if count >= 2]
    filtered.sort(key=lambda x: (-x[1], x[0]))

    return [entity for entity, _ in filtered[:10]]


def extract_topic_terms(title: str, h1: str) -> set[str]:
    combined = f"{title} {h1}".lower()
    return set(re.findall(r"\b[a-zA-Z]{4,}\b", combined))


def count_topic_overlap(text: str, title: str, h1: str) -> int:
    topic_terms = extract_topic_terms(title, h1)
    text_terms = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    counts = Counter(text_terms)
    return sum(1 for term in topic_terms if counts[term] >= 2)


# -----------------------------
# Fetch validation
# -----------------------------
def validate_fetch(
    response,
    soup: BeautifulSoup,
    visible_text: str,
    title: str,
    h1_tags,
    h2_tags,
    internal_links: int,
) -> dict:
    warnings = []
    signals = []

    word_count = len(visible_text.split())
    content_type = response.headers.get("Content-Type", "")

    if response.status_code != 200:
        warnings.append(f"Expected 200 OK but received {response.status_code}.")
    else:
        signals.append("Returned HTTP 200.")

    if "text/html" not in content_type.lower():
        warnings.append(f"Response content type may not be standard HTML: {content_type or 'Unknown'}.")
    else:
        signals.append("Returned HTML content.")

    if not title:
        warnings.append("No title detected in fetched HTML.")
    else:
        signals.append("Title detected.")

    if len(h1_tags) == 0:
        warnings.append("No H1 detected in fetched HTML.")
    else:
        signals.append("H1 detected.")

    if word_count < 50:
        warnings.append("Very little visible text was extracted from the fetched HTML.")
    elif word_count < 150:
        warnings.append("Only limited visible text was extracted from the fetched HTML.")
        signals.append("Some visible text detected.")
    else:
        signals.append("Sufficient visible text detected.")

    if len(h2_tags) == 0:
        warnings.append("No H2 headings detected in fetched HTML.")
    else:
        signals.append("H2 headings detected.")

    if internal_links == 0:
        warnings.append("No internal links detected in fetched HTML.")
    else:
        signals.append("Internal links detected.")

    low_confidence_patterns = [
        word_count < 50 and not title and len(h1_tags) == 0,
        response.status_code != 200 and word_count < 150,
    ]

    medium_confidence_patterns = [
        response.status_code == 200 and word_count < 150,
        response.status_code != 200 and word_count >= 150,
    ]

    if any(low_confidence_patterns):
        confidence = "Low"
        valid_for_scoring = False
        summary = (
            "The fetched response does not appear to contain enough representative page content "
            "for a reliable audit."
        )
    elif any(medium_confidence_patterns):
        confidence = "Medium"
        valid_for_scoring = True
        summary = (
            "The page was fetched, but the extracted content looks partial or limited. "
            "Scores should be treated with caution."
        )
    else:
        confidence = "High"
        valid_for_scoring = True
        summary = "The fetched page appears representative enough for a standard MVP audit."

    return {
        "confidence": confidence,
        "valid_for_scoring": valid_for_scoring,
        "warnings": warnings,
        "signals": signals,
        "summary": summary,
    }


# -----------------------------
# Scoring
# -----------------------------
def score_structure(title: str, meta_description: str, h1_tags, h2_tags) -> tuple[int, list[str]]:
    score = 0
    notes = []

    title_len = len(title.strip())
    if title:
        score += 2
    else:
        notes.append("Missing title tag.")

    if 20 <= title_len <= 65:
        score += 1
    elif title:
        notes.append("Title length could be improved for clarity.")

    if meta_description:
        score += 1
    else:
        notes.append("Missing meta description.")

    if len(h1_tags) == 1:
        score += 3
    elif len(h1_tags) == 0:
        notes.append("No H1 found.")
    else:
        score += 1
        notes.append("Multiple H1s found.")

    if len(h2_tags) >= 2:
        score += 2
    else:
        notes.append("Not enough H2 subheadings.")

    first_h1 = h1_tags[0].get_text(" ", strip=True) if h1_tags else ""
    if len(first_h1.split()) >= 3:
        score += 1
    elif first_h1:
        notes.append("H1 is present but may be too vague.")

    return min(score, 10), notes


def score_crawlability(
    status_code: int,
    noindex: bool,
    nofollow: bool,
    canonical_present: bool,
    content_type: str
) -> tuple[int, list[str]]:
    score = 0
    notes = []

    if status_code == 200:
        score += 4
    elif 200 <= status_code < 300:
        score += 3
    elif 300 <= status_code < 400:
        score += 2
        notes.append("Page resolves via redirect.")
    else:
        notes.append("Page did not return a successful status.")

    if canonical_present:
        score += 2
    else:
        notes.append("Missing canonical tag.")

    if not noindex:
        score += 2
    else:
        notes.append("Page has a noindex directive.")

    if not nofollow:
        score += 1
    else:
        notes.append("Page has a nofollow directive.")

    if "text/html" in content_type.lower():
        score += 1
    else:
        notes.append("Response may not be standard HTML content.")

    return min(score, 10), notes


def score_internal_linking(internal_links: int, external_links: int) -> tuple[int, list[str]]:
    notes = []

    if internal_links >= 15:
        score = 10
    elif internal_links >= 8:
        score = 8
    elif internal_links >= 4:
        score = 6
    elif internal_links >= 1:
        score = 3
    else:
        score = 0
        notes.append("No internal links found.")

    if external_links > internal_links * 2 and internal_links < 3:
        score = max(0, score - 1)
        notes.append("Page relies more on external than internal linking.")

    return score, notes


def score_clarity(text: str, h2_count: int = 0) -> tuple[int, list[str]]:
    notes = []

    words = text.split()
    word_count = len(words)
    sentences = split_sentences(text)
    avg_sentence_length = get_avg_sentence_length(text)

    score = 0

    if word_count >= 250:
        score += 3
    elif word_count >= 120:
        score += 2
    elif word_count >= 60:
        score += 1
    else:
        notes.append("Content may be too thin for reliable AI summarisation.")

    if 8 <= avg_sentence_length <= 22:
        score += 4
    elif 6 <= avg_sentence_length <= 28:
        score += 2
    else:
        notes.append("Sentence length may reduce clarity.")

    if h2_count >= 2:
        score += 2
    elif h2_count == 1:
        score += 1

    if len(sentences) >= 5:
        score += 1

    return min(score, 10), notes


def score_answer_focus(text: str) -> tuple[int, list[str]]:
    notes = []
    text_lower = text.lower()

    patterns = {
        "definition": r"\b(is|are|refers to|means)\b",
        "how_to": r"\bhow to\b",
        "question_words": r"\b(what|how|why|when|where|which|who)\b",
        "faq": r"\bfaq\b|\bfrequently asked questions\b",
        "benefits": r"\bbenefits?\b|\badvantages?\b",
        "steps": r"\bsteps?\b|\bprocess\b|\bguide\b",
    }

    matches = sum(1 for pattern in patterns.values() if re.search(pattern, text_lower))

    if matches >= 5:
        score = 10
    elif matches == 4:
        score = 8
    elif matches == 3:
        score = 6
    elif matches == 2:
        score = 4
    elif matches == 1:
        score = 2
    else:
        score = 0
        notes.append("Page does not strongly signal answer-oriented content.")

    return score, notes


def score_entity_relevance(entities: list[str], text: str, title: str, h1: str) -> tuple[int, list[str]]:
    notes = []
    score = 0

    if len(entities) >= 8:
        score += 6
    elif len(entities) >= 5:
        score += 5
    elif len(entities) >= 3:
        score += 4
    elif len(entities) >= 1:
        score += 2
    else:
        notes.append("Very few meaningful entities detected.")

    overlap = count_topic_overlap(text, title, h1)
    if overlap >= 3:
        score += 4
    elif overlap >= 1:
        score += 2
    else:
        notes.append("Main topic terms are not strongly reinforced in the page copy.")

    return min(score, 10), notes


def overall_score(scores: dict) -> tuple[float, float, float]:
    technical = round(
        (scores["structure"] + scores["crawlability"] + scores["internal_linking"]) / 3,
        1
    )
    content = round(
        (scores["clarity"] + scores["answer_focus"] + scores["entity_relevance"]) / 3,
        1
    )
    overall = round((technical * 0.45 + content * 0.55) * 10, 1)
    return overall, technical, content


# -----------------------------
# Recommendations / summaries
# -----------------------------
def generate_recommendations(data: dict) -> list[dict]:
    recs = []

    def add(priority: str, category: str, message: str, impact: str):
        recs.append({
            "priority": priority,
            "category": category,
            "message": message,
            "impact": impact,
        })

    if data["fetch_confidence"] == "Low":
        add(
            "High",
            "Fetch Reliability",
            "Retry this page with a stronger fetch method or browser-rendered mode before trusting the audit result.",
            "Prevents false low scores caused by partial or blocked responses."
        )
        add(
            "High",
            "Fetch Reliability",
            "Treat this result as inconclusive because the fetched HTML did not contain enough representative content.",
            "Improves trust in the product by separating page quality from fetch quality."
        )
        return recs

    if data["structure_score"] is not None and data["structure_score"] <= 5:
        if not data["title"]:
            add(
                "High",
                "Structure",
                "Add a title tag that states the page topic clearly and specifically.",
                "Helps AI systems identify the topic quickly."
            )
        if data["h1_count"] != 1:
            add(
                "High",
                "Structure",
                "Use exactly one clear H1 so machines can recognise the main page intent.",
                "Improves topical clarity for summarisation."
            )
        if data["h2_count"] < 2:
            add(
                "Medium",
                "Structure",
                "Break the page into clearer H2 sections to improve scanability.",
                "Makes the content easier for AI systems to segment and summarise."
            )

    if data["crawlability_score"] is not None and data["crawlability_score"] <= 6:
        if not data["canonical"]:
            add(
                "High",
                "Crawlability",
                "Add a canonical tag to clarify the preferred version of the page.",
                "Reduces ambiguity for indexing and page interpretation."
            )
        if data["noindex"]:
            add(
                "High",
                "Crawlability",
                "Remove the noindex directive if this page is meant to be discoverable.",
                "Prevents the page being excluded from search visibility."
            )
        if data["nofollow"]:
            add(
                "Medium",
                "Crawlability",
                "Review the nofollow directive if the page should contribute to site context.",
                "Can improve how linked content is interpreted."
            )

    if data["internal_linking_score"] is not None and data["internal_linking_score"] <= 4:
        add(
            "Medium",
            "Linking",
            "Add more relevant internal links to supporting pages and related content.",
            "Strengthens content context and crawl paths."
        )

    if data["clarity_score"] is not None and data["clarity_score"] <= 5:
        add(
            "High",
            "Content Clarity",
            "Rewrite dense sections into shorter, more direct sentences and clearer paragraphs.",
            "Makes summarisation easier for both users and AI systems."
        )

    if data["answer_focus_score"] is not None and data["answer_focus_score"] <= 4:
        add(
            "High",
            "Answer Focus",
            "Add definition-style copy, FAQs, or direct question-and-answer sections near the top.",
            "Helps AI systems extract concise answers."
        )

    if data["entity_relevance_score"] is not None and data["entity_relevance_score"] <= 5:
        add(
            "Medium",
            "Entity Relevance",
            "Include more specific entities, product names, concepts, and repeated contextual terms.",
            "Improves topical specificity and retrieval relevance."
        )

    if not data["structured_data_present"]:
        add(
            "Medium",
            "Structured Data",
            "Add relevant schema such as Article, FAQ, Product, or Breadcrumb markup.",
            "Gives machines stronger context signals."
        )

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 9))

    return recs[:5]


def score_band(score: float | None) -> str:
    if score is None:
        return "Unscored"
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Moderate"
    return "Weak"


def generate_audit_summary(data: dict) -> str:
    if data["fetch_confidence"] == "Low":
        return (
            "This page could not be reliably audited because the fetched response did not "
            "contain enough representative content. The result should be treated as inconclusive, "
            "not as a true measure of AI visibility."
        )

    band = score_band(data["overall_ai_visibility_score"])

    strengths = []
    weaknesses = []

    if data["structure_score"] is not None and data["structure_score"] >= 7:
        strengths.append("the page structure is reasonably clear")
    else:
        weaknesses.append("the structural signals are weak")

    if data["crawlability_score"] is not None and data["crawlability_score"] >= 7:
        strengths.append("the page appears crawl-friendly")
    else:
        weaknesses.append("crawlability signals need improvement")

    if data["clarity_score"] is not None and data["clarity_score"] >= 7:
        strengths.append("the copy is relatively easy to process")
    else:
        weaknesses.append("the content could be clearer and easier to summarise")

    if data["answer_focus_score"] is not None and data["answer_focus_score"] >= 6:
        strengths.append("the page includes answer-oriented language")
    else:
        weaknesses.append("the page does not strongly present answer-focused content")

    if data["entity_relevance_score"] is not None and data["entity_relevance_score"] >= 6:
        strengths.append("the topic is reinforced by relevant entities and terms")
    else:
        weaknesses.append("the topic could be reinforced with more specific entities")

    strengths_text = ", ".join(strengths[:3]) if strengths else "there are limited strong signals"
    weaknesses_text = ", ".join(weaknesses[:3]) if weaknesses else "there are no major weaknesses detected"

    caution = ""
    if data["fetch_confidence"] == "Medium":
        caution = " The fetch looked partial, so treat the score with some caution."

    return (
        f"This page has {band.lower()} AI visibility with a score of "
        f"{data['overall_ai_visibility_score']}/100. On the positive side, "
        f"{strengths_text}. The main opportunities are that {weaknesses_text}.{caution}"
    )


# -----------------------------
# Main audit pipeline
# -----------------------------
def audit_url(url: str):
    response = fetch_page(url)
    html = response.text
    soup = BeautifulSoup(html, "lxml")

    title = soup.title.get_text(strip=True) if soup.title else ""
    meta_description = extract_meta_content(soup, name="description")
    robots = extract_meta_content(soup, name="robots")
    canonical = extract_canonical(soup)

    h1_tags = soup.find_all("h1")
    h2_tags = soup.find_all("h2")
    h1_text = h1_tags[0].get_text(" ", strip=True) if h1_tags else ""

    visible_text = extract_visible_text(soup)
    content_sample = visible_text[:7000]
    word_count = len(visible_text.split())
    avg_sentence_length = round(get_avg_sentence_length(content_sample), 1)

    internal_links, external_links = count_links(soup, str(response.url))
    structured = detect_structured_data(soup)

    entities = extract_entities_simple(content_sample, title=title, h1=h1_text)

    noindex = "noindex" in robots.lower()
    nofollow = "nofollow" in robots.lower()
    content_type = response.headers.get("Content-Type", "")

    fetch_validation = validate_fetch(
        response=response,
        soup=soup,
        visible_text=visible_text,
        title=title,
        h1_tags=h1_tags,
        h2_tags=h2_tags,
        internal_links=internal_links,
    )

    result = {
        "page": {
            "input_url": url,
            "final_url": str(response.url),
            "status_code": response.status_code,
            "content_type": content_type,
            "title": title,
            "meta_description": meta_description,
            "canonical": canonical,
            "robots": robots,
            "noindex": noindex,
            "nofollow": nofollow,
            "h1": h1_text,
            "h1_count": len(h1_tags),
            "h2_count": len(h2_tags),
            "word_count": word_count,
            "avg_sentence_length": avg_sentence_length,
            "internal_links": internal_links,
            "external_links": external_links,
            "structured_data_present": structured["present"],
            "structured_data_types": structured["types"],
            "entities": entities,
        },
        "fetch_validation": fetch_validation,
        "scores": {},
        "notes": {},
        "future_llm_summary": None,
    }

    if not fetch_validation["valid_for_scoring"]:
        result["scores"] = {
            "structure_score": None,
            "crawlability_score": None,
            "internal_linking_score": None,
            "clarity_score": None,
            "answer_focus_score": None,
            "entity_relevance_score": None,
            "technical_score": None,
            "content_score": None,
            "overall_ai_visibility_score": None,
            "score_band": "Unscored",
        }
        result["notes"] = {
            "structure_notes": [],
            "crawlability_notes": [],
            "linking_notes": [],
            "clarity_notes": [],
            "answer_focus_notes": [],
            "entity_notes": [],
        }
    else:
        structure_score, structure_notes = score_structure(title, meta_description, h1_tags, h2_tags)
        crawlability_score, crawlability_notes = score_crawlability(
            response.status_code,
            noindex,
            nofollow,
            bool(canonical),
            content_type
        )
        internal_linking_score, linking_notes = score_internal_linking(internal_links, external_links)
        clarity_score, clarity_notes = score_clarity(content_sample, h2_count=len(h2_tags))
        answer_focus_score, answer_notes = score_answer_focus(content_sample)
        entity_relevance_score, entity_notes = score_entity_relevance(entities, content_sample, title, h1_text)

        scores = {
            "structure": structure_score,
            "crawlability": crawlability_score,
            "internal_linking": internal_linking_score,
            "clarity": clarity_score,
            "answer_focus": answer_focus_score,
            "entity_relevance": entity_relevance_score,
        }

        final_score, technical_score, content_score = overall_score(scores)

        result["scores"] = {
            "structure_score": structure_score,
            "crawlability_score": crawlability_score,
            "internal_linking_score": internal_linking_score,
            "clarity_score": clarity_score,
            "answer_focus_score": answer_focus_score,
            "entity_relevance_score": entity_relevance_score,
            "technical_score": technical_score,
            "content_score": content_score,
            "overall_ai_visibility_score": final_score,
            "score_band": score_band(final_score),
        }
        result["notes"] = {
            "structure_notes": structure_notes,
            "crawlability_notes": crawlability_notes,
            "linking_notes": linking_notes,
            "clarity_notes": clarity_notes,
            "answer_focus_notes": answer_notes,
            "entity_notes": entity_notes,
        }

    flattened = {
        **result["page"],
        **result["scores"],
        **result["notes"],
        "fetch_confidence": fetch_validation["confidence"],
        "fetch_valid_for_scoring": fetch_validation["valid_for_scoring"],
        "fetch_warnings": fetch_validation["warnings"],
        "fetch_signals": fetch_validation["signals"],
        "fetch_summary": fetch_validation["summary"],
        "recommendations": [],
        "audit_summary": "",
    }

    flattened["recommendations"] = generate_recommendations(flattened)
    flattened["audit_summary"] = generate_audit_summary(flattened)

    result["recommendations"] = flattened["recommendations"]
    result["audit_summary"] = flattened["audit_summary"]
    result["flat"] = flattened

    return result