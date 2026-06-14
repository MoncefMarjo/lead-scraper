"""
dm_hunter.py
Step 2 — Decision-maker phone hunter
Sources: Google Search, Company website, LinkedIn (public), Pages Jaunes
Returns: list of phones with source, type, and raw confidence score
"""

import re
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from googlesearch import search

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# French phone regex — matches 0X XX XX XX XX and +33 X XX XX XX XX
PHONE_RE = re.compile(
    r"(?:(?:\+33|0033)\s?[1-9](?:[\s.\-]?\d{2}){4}|0[1-9](?:[\s.\-]?\d{2}){4})"
)

# Source weights for confidence scoring
SOURCE_WEIGHTS = {
    "linkedin":        75,
    "website_team":    70,
    "website_contact": 55,
    "google_search":   55,
    "pages_jaunes":    35,
}

# ── Phone Utilities ───────────────────────────────────────────────────────────

def normalize_phone(raw: str) -> str:
    """Normalize any French phone to 0X XX XX XX XX format."""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("33") and len(digits) == 11:
        digits = "0" + digits[2:]
    if len(digits) == 10:
        return " ".join([digits[i:i+2] for i in range(0, 10, 2)])
    return ""


def phone_type(normalized: str) -> str:
    """Classify phone as Mobile, Fixe, or Special."""
    prefix = normalized.replace(" ", "")[:2]
    if prefix in ("06", "07"):
        return "Mobile"
    elif prefix in ("01", "02", "03", "04", "05"):
        return "Fixe"
    elif prefix.startswith("08"):
        return "Special"
    return "Inconnu"


def extract_phones(text: str) -> list:
    """Extract and normalize all phones found in a text block."""
    found = PHONE_RE.findall(text)
    phones = []
    for raw in found:
        norm = normalize_phone(raw)
        if norm:
            phones.append(norm)
    return list(set(phones))


def safe_get(url: str, timeout: int = 8) -> str:
    """Fetch a URL and return its text content, or empty string on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return ""


def random_delay():
    """Polite random delay between requests."""
    time.sleep(random.uniform(2.0, 4.5))


# ── Source 1: Google Search ───────────────────────────────────────────────────

def hunt_google(company: str, ceo: str, city: str = "") -> list:
    """
    Search Google for CEO + company + phone mentions.
    Returns list of {phone, source, score} dicts.
    """
    results = []
    queries = []

    if ceo and ceo != "N/A":
        queries.append(f'"{ceo}" "{company}" téléphone')
        queries.append(f'"{ceo}" "{company}" contact')
    queries.append(f'"{company}" {city} dirigeant téléphone direct')

    seen_urls = set()

    for query in queries:
        try:
            logger.info(f"Google search: {query}")
            urls = list(search(query, num_results=5, lang="fr"))
            random_delay()

            for url in urls:
                # Skip LinkedIn here (handled separately)
                if "linkedin.com" in url or url in seen_urls:
                    continue
                seen_urls.add(url)

                html = safe_get(url)
                if not html:
                    continue

                soup = BeautifulSoup(html, "lxml")
                text = soup.get_text(separator=" ")
                phones = extract_phones(text)

                for phone in phones:
                    ptype = phone_type(phone)
                    # Only keep mobile and fixe from Google Search
                    if ptype in ("Mobile", "Fixe"):
                        score = SOURCE_WEIGHTS["google_search"]
                        # Bonus if mobile (more likely to be direct)
                        if ptype == "Mobile":
                            score += 10
                        # Bonus if CEO name appears near the phone
                        if ceo and ceo != "N/A" and ceo.split()[0].lower() in text.lower():
                            score += 15
                        results.append({
                            "phone": phone,
                            "source": "Google Search",
                            "source_key": "google_search",
                            "type": ptype,
                            "score": min(score, 99),
                            "url": url,
                        })
                random_delay()

        except Exception as e:
            logger.warning(f"Google search failed for '{query}': {e}")

    return results


# ── Source 2: Company Website ─────────────────────────────────────────────────

def hunt_website(website_url: str, ceo: str = "") -> list:
    """
    Scrape company website — specifically team/contact/about pages.
    Returns list of {phone, source, score} dicts.
    """
    if not website_url or website_url == "N/A":
        return []

    results = []
    base = website_url.rstrip("/")

    # Pages most likely to have direct numbers
    target_paths = [
        "/equipe", "/direction", "/dirigeants",
        "/contact", "/nous-contacter", "/about", "/a-propos",
        "/team", "/management",
    ]

    for path in target_paths:
        url = base + path
        html = safe_get(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator=" ")
        phones = extract_phones(text)

        # Determine if this is a team page or contact page
        is_team_page = any(k in path for k in ["/equipe", "/direction", "/dirigeants", "/team", "/management"])
        source_key = "website_team" if is_team_page else "website_contact"

        for phone in phones:
            ptype = phone_type(phone)
            if ptype in ("Mobile", "Fixe"):
                score = SOURCE_WEIGHTS[source_key]
                if ptype == "Mobile":
                    score += 10
                if ceo and ceo != "N/A" and ceo.split()[0].lower() in text.lower():
                    score += 15
                results.append({
                    "phone": phone,
                    "source": f"Website ({path})",
                    "source_key": source_key,
                    "type": ptype,
                    "score": min(score, 99),
                    "url": url,
                })

        random_delay()

    return results


# ── Source 3: LinkedIn (public pages only) ────────────────────────────────────

def hunt_linkedin(company: str, ceo: str, city: str = "") -> list:
    """
    Use Google to find LinkedIn pages, then scrape public content only.
    Returns list of {phone, source, score} dicts.
    """
    results = []
    queries = []

    if ceo and ceo != "N/A":
        queries.append(f'site:linkedin.com/in "{ceo}" "{company}" téléphone')
    queries.append(f'site:linkedin.com/company "{company}" {city} téléphone')

    for query in queries:
        try:
            logger.info(f"LinkedIn via Google: {query}")
            urls = list(search(query, num_results=3, lang="fr"))
            random_delay()

            for url in urls:
                if "linkedin.com" not in url:
                    continue

                html = safe_get(url)
                if not html:
                    continue

                soup = BeautifulSoup(html, "lxml")
                text = soup.get_text(separator=" ")
                phones = extract_phones(text)

                for phone in phones:
                    ptype = phone_type(phone)
                    if ptype in ("Mobile", "Fixe"):
                        score = SOURCE_WEIGHTS["linkedin"]
                        if ptype == "Mobile":
                            score += 10
                        if ceo and ceo != "N/A" and ceo.split()[0].lower() in text.lower():
                            score += 10
                        results.append({
                            "phone": phone,
                            "source": "LinkedIn",
                            "source_key": "linkedin",
                            "type": ptype,
                            "score": min(score, 99),
                            "url": url,
                        })
                random_delay()

        except Exception as e:
            logger.warning(f"LinkedIn search failed for '{query}': {e}")

    return results


# ── Source 4: Pages Jaunes ────────────────────────────────────────────────────

def hunt_pages_jaunes(company: str, city: str = "") -> list:
    """
    Scrape Pages Jaunes — low confidence, switchboard risk.
    Only used as a last resort fallback.
    Returns list of {phone, source, score} dicts.
    """
    results = []
    query = f"{company} {city}".strip().replace(" ", "+")
    url = f"https://www.pagesjaunes.fr/pagesblanches/recherche?quoiqui={query}"

    html = safe_get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")
    phones = extract_phones(text)

    for phone in phones:
        ptype = phone_type(phone)
        if ptype in ("Mobile", "Fixe"):
            results.append({
                "phone": phone,
                "source": "Pages Jaunes",
                "source_key": "pages_jaunes",
                "type": ptype,
                "score": SOURCE_WEIGHTS["pages_jaunes"],
                "url": url,
            })

    return results


# ── Cross-Source Reconciliation ───────────────────────────────────────────────

def reconcile(all_results: list) -> list:
    """
    Merge all phone results, deduplicate, and apply cross-source bonus.
    Returns sorted list of unique phones with final confidence score.
    """
    phone_map = {}

    for r in all_results:
        phone = r["phone"]
        if phone not in phone_map:
            phone_map[phone] = {
                "phone": phone,
                "type": r["type"],
                "sources": [],
                "source_keys": set(),
                "best_score": 0,
                "urls": [],
            }
        entry = phone_map[phone]
        entry["sources"].append(r["source"])
        entry["source_keys"].add(r["source_key"])
        entry["urls"].append(r["url"])
        entry["best_score"] = max(entry["best_score"], r["score"])

    # Apply cross-source bonus
    final = []
    for phone, data in phone_map.items():
        score = data["best_score"]
        n_sources = len(data["source_keys"])
        if n_sources >= 2:
            score = min(score + 15 * (n_sources - 1), 99)
        final.append({
            "phone": phone,
            "type": data["type"],
            "sources": ", ".join(set(data["sources"])),
            "confidence": score,
        })

    # Sort by confidence descending
    final.sort(key=lambda x: x["confidence"], reverse=True)
    return final


# ── Main Hunt Function ────────────────────────────────────────────────────────

def hunt_dm_phones(company: str, ceo: str, city: str = "", website: str = "N/A") -> list:
    """
    Full decision-maker phone hunt across all sources.

    Args:
        company: Company name
        ceo:     CEO/Gérant name from identity step
        city:    City for search narrowing
        website: Company website URL if known

    Returns:
        List of reconciled phone dicts sorted by confidence
    """
    logger.info(f"🔍 Hunting phones for: {company} | CEO: {ceo}")
    all_results = []

    # Source 1: Google Search
    all_results += hunt_google(company, ceo, city)

    # Source 2: Company Website
    if website and website != "N/A":
        all_results += hunt_website(website, ceo)

    # Source 3: LinkedIn (public)
    all_results += hunt_linkedin(company, ceo, city)

    # Source 4: Pages Jaunes (fallback)
    all_results += hunt_pages_jaunes(company, city)

    # Reconcile and score
    final = reconcile(all_results)

    if final:
        logger.info(f"✅ Found {len(final)} unique phone(s) for {company}")
    else:
        logger.warning(f"❌ No phones found for {company}")

    return final


# ── Quick Test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test = {
        "company": "Boulangerie Dupont",
        "ceo": "PUTHET",
        "city": "Lyon",
        "website": "N/A",
    }

    print(f"\n=== DM PHONE HUNT TEST ===\n")
    phones = hunt_dm_phones(
        company=test["company"],
        ceo=test["ceo"],
        city=test["city"],
        website=test["website"],
    )

    if phones:
        for p in phones:
            print(f"📞 {p['phone']} | {p['type']} | {p['confidence']}% | {p['sources']}")
    else:
        print("No phones found.")