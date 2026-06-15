"""
dm_hunter.py
Step 2 — Decision-maker phone hunter
Sources: Google Search, Company website, LinkedIn, Google Maps (Selenium)
"""

import re
import time
import random
import logging
import urllib.parse
import requests
from bs4 import BeautifulSoup
from googlesearch import search
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

PHONE_RE = re.compile(
    r"(?:(?:\+33|0033)\s?[1-9](?:[\s.\-]?\d{2}){4}|0[1-9](?:[\s.\-]?\d{2}){4})"
)

SOURCE_WEIGHTS = {
    "linkedin":        75,
    "website_team":    70,
    "website_contact": 55,
    "google_search":   55,
    "google_maps":     45,
    "pages_jaunes":    35,
}


# ── Phone Utilities ───────────────────────────────────────────────────────────

def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("33") and len(digits) == 11:
        digits = "0" + digits[2:]
    if len(digits) == 10:
        return " ".join([digits[i:i+2] for i in range(0, 10, 2)])
    return ""


def phone_type(normalized: str) -> str:
    prefix = normalized.replace(" ", "")[:2]
    if prefix in ("06", "07"):
        return "Mobile"
    elif prefix in ("01", "02", "03", "04", "05"):
        return "Fixe"
    elif prefix.startswith("08"):
        return "Special"
    return "Inconnu"


def extract_phones(text: str) -> list:
    found = PHONE_RE.findall(text)
    phones = []
    for raw in found:
        norm = normalize_phone(raw)
        if norm:
            phones.append(norm)
    return list(set(phones))


def safe_get(url: str, timeout: int = 8) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return ""


def random_delay():
    time.sleep(random.uniform(2.0, 4.0))


# ── Source 1: Google Search ───────────────────────────────────────────────────

def hunt_google(company: str, ceo: str, city: str = "") -> list:
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
                    if ptype in ("Mobile", "Fixe"):
                        score = SOURCE_WEIGHTS["google_search"]
                        if ptype == "Mobile":
                            score += 10
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
    if not website_url or website_url == "N/A":
        return []

    results = []
    base = website_url.rstrip("/")
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


# ── Source 3: LinkedIn ────────────────────────────────────────────────────────

def hunt_linkedin(company: str, ceo: str, city: str = "") -> list:
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


# ── Source 4: Google Maps via Selenium ───────────────────────────────────────

def hunt_maps_selenium(company: str, city: str = "") -> list:
    """Extract phone directly from Google Maps using Selenium."""
    results = []
    if not SELENIUM_AVAILABLE:
        logger.warning("Selenium not available — skipping Maps hunt")
        return []
    query = urllib.parse.quote_plus(f"{company} {city}")
    url = f"https://www.google.com/maps/search/{query}"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=fr")

    try:
        driver = webdriver.Chrome(
            service=Service("chromedriver.exe"),
            options=options
        )
        driver.set_page_load_timeout(15)
        driver.get(url)
        time.sleep(3)

        page_text = driver.find_element(By.TAG_NAME, "body").text
        phones_found = extract_phones(page_text)

        for ph in phones_found:
            norm = normalize_phone(ph)
            if norm:
                ptype = phone_type(norm)
                results.append({
                    "phone": norm,
                    "source": "Google Maps",
                    "source_key": "google_maps",
                    "type": ptype,
                    "score": SOURCE_WEIGHTS["google_maps"],
                    "url": url,
                })
                logger.info(f"📍 Maps phone found: {norm}")

        if not phones_found:
            logger.warning(f"No phone on Maps for: {company}")

        driver.quit()

    except Exception as e:
        logger.warning(f"Selenium Maps failed for {company}: {e}")

    return results


# ── Source 5: Pages Jaunes ────────────────────────────────────────────────────

def hunt_pages_jaunes(company: str, city: str = "") -> list:
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


# ── Reconciliation ────────────────────────────────────────────────────────────

def reconcile(all_results: list) -> list:
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

    final.sort(key=lambda x: x["confidence"], reverse=True)
    return final


# ── Main Hunt Function ────────────────────────────────────────────────────────

def hunt_dm_phones(company: str, ceo: str, city: str = "", website: str = "N/A") -> list:
    logger.info(f"🔍 Hunting phones for: {company} | CEO: {ceo}")
    all_results = []

    # Source 1: Google Search
    all_results += hunt_google(company, ceo, city)

    # Source 2: Company Website
    if website and website != "N/A":
        all_results += hunt_website(website, ceo)

    # Source 3: LinkedIn
    all_results += hunt_linkedin(company, ceo, city)

    # Source 4: Google Maps via Selenium
    all_results += hunt_maps_selenium(company, city)

    # Source 5: Pages Jaunes (fallback)
    all_results += hunt_pages_jaunes(company, city)

    final = reconcile(all_results)

    if final:
        logger.info(f"✅ Found {len(final)} unique phone(s) for {company}")
    else:
        logger.warning(f"❌ No phones found for {company}")

    return final