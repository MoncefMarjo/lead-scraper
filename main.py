"""
main.py — B2B Lead Scraper — Final Solution
Strategy:
1. Discover companies via SIRENE API (by NAF + postal code)
2. For each company, search Google Maps ONCE via Selenium (batch mode)
3. Extract phone directly from Maps listing
4. Enrich with SIREN/SIRET/CEO from govt API
5. Export to Excel with confidence score
"""

import time
import logging
import urllib.parse
import requests
import re
from export.excel import export_to_excel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Phone utilities ───────────────────────────────────────────────────────────

PHONE_RE = re.compile(
    r"(?:(?:\+33|0033)\s?[1-9](?:[\s.\-]?\d{2}){4}|0[1-9](?:[\s.\-]?\d{2}){4})"
)

def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("33") and len(digits) == 11:
        digits = "0" + digits[2:]
    if len(digits) == 10:
        return " ".join([digits[i:i+2] for i in range(0, 10, 2)])
    return ""

def phone_type(normalized: str) -> str:
    prefix = normalized.replace(" ", "")[:2]
    if prefix in ("06", "07"): return "Mobile"
    if prefix in ("01","02","03","04","05"): return "Fixe"
    return "Autre"

# ── Step 1: Discover companies via SIRENE ────────────────────────────────────

def discover_companies(naf_code: str, postal_codes: list, target: int = 500) -> list:
    API = "https://recherche-entreprises.api.gouv.fr/search"
    seen = set()
    leads = []
    cycles = 0

    logger.info(f"🔍 Discovery: NAF={naf_code} | Target={target}")

    while len(leads) < target:
        if cycles >= 3:
            logger.warning("Max cycles reached")
            break

        for cp in postal_codes:
            if len(leads) >= target:
                break
            page = 1
            while len(leads) < target:
                try:
                    r = requests.get(API, params={
                        "activite_principale": naf_code,
                        "code_postal": cp,
                        "per_page": 25,
                        "page": page,
                    }, timeout=10)
                    r.raise_for_status()
                    data = r.json()
                    results = data.get("results", [])
                    if not results:
                        break

                    for c in results:
                        if len(leads) >= target:
                            break
                        siege = c.get("siege", {})
                        siret = siege.get("siret", "")
                        if not siret or siret in seen:
                            continue
                        nom = (c.get("nom_raison_sociale") or c.get("nom_complet") or "").split("(")[0].strip()
                        if not nom:
                            continue
                        seen.add(siret)
                        leads.append({
                            "nom": nom,
                            "siren": c.get("siren", "N/A"),
                            "siret": siret,
                            "naf": naf_code,
                            "ceo": _extract_ceo(c.get("dirigeants", [])),
                            "address": siege.get("adresse", "N/A"),
                            "city": siege.get("libelle_commune", ""),
                            "website": siege.get("site_internet", "N/A") or "N/A",
                        })
                        logger.info(f"[{len(leads)}/{target}] {nom}")

                    total = data.get("total_results", 0)
                    if page * 25 >= total:
                        break
                    page += 1
                    time.sleep(0.3)

                except Exception as e:
                    logger.warning(f"API error {cp}: {e}")
                    break

        cycles += 1

    logger.info(f"✅ Discovered {len(leads)} companies")
    return leads


def _extract_ceo(dirigeants: list) -> str:
    priority = ["gérant", "président", "directeur général", "pdg"]
    physical = [d for d in dirigeants if d.get("type_dirigeant") == "personne physique"]
    if not physical:
        return "N/A"
    for d in physical:
        role = d.get("qualite", "").lower()
        if any(p in role for p in priority):
            prenom = d.get("prenom", "").strip().title()
            nom = d.get("nom", "").strip().upper().split("(")[0].strip()
            return f"{prenom} {nom}".strip() or "N/A"
    d = physical[0]
    prenom = d.get("prenom", "").strip().title()
    nom = d.get("nom", "").strip().upper().split("(")[0].strip()
    return f"{prenom} {nom}".strip() or "N/A"


# ── Step 2: Batch Maps scraping via Selenium ─────────────────────────────────

def batch_maps_phones(companies: list, job: dict = None) -> list:
    """
    Open Chrome ONCE, search each company on Maps, extract phone.
    Returns enriched companies with phone added.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        logger.warning("Selenium not available — skipping Maps")
        return companies

    logger.info("🌐 Starting batch Maps scraping...")

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=fr")
    options.add_argument("--log-level=3")

    try:
        driver = webdriver.Chrome(service=Service("chromedriver.exe"), options=options)
        driver.set_page_load_timeout(15)
    except Exception as e:
        logger.warning(f"Chrome failed to start: {e}")
        return companies

    # Accept cookies once
    try:
        driver.get("https://www.google.com/maps")
        time.sleep(2)
        btns = driver.find_elements(By.XPATH, '//button')
        for btn in btns:
            if "accepter" in btn.text.lower() or "accept" in btn.text.lower():
                btn.click()
                break
        time.sleep(1)
    except:
        pass

    for i, company in enumerate(companies):
        try:
            query = urllib.parse.quote_plus(f"{company['nom']} {company['city']}")
            url = f"https://www.google.com/maps/search/{query}"
            driver.get(url)
            time.sleep(3)

            page_text = driver.find_element(By.TAG_NAME, "body").text
            found = PHONE_RE.findall(page_text)

            phones = []
            seen_phones = set()
            for raw in found:
                norm = normalize_phone(raw)
                if norm and norm not in seen_phones:
                    seen_phones.add(norm)
                    phones.append({
                        "phone": norm,
                        "type": phone_type(norm),
                        "confidence": 45,
                        "sources": "Google Maps",
                    })

            company["phones"] = phones

            if phones:
                logger.info(f"[{i+1}/{len(companies)}] ✅ {company['nom']} → {phones[0]['phone']}")
            else:
                logger.info(f"[{i+1}/{len(companies)}] ❌ {company['nom']} → no phone")

            if job:
                job["progress"] = i + 1
                job["current"] = company["nom"]
                job["with_phone"] = sum(1 for c in companies if c.get("phones"))

        except Exception as e:
            logger.warning(f"Maps error for {company['nom']}: {e}")
            company["phones"] = []

    try:
        driver.quit()
    except:
        pass

    return companies


# ── Step 3: Export to Excel ───────────────────────────────────────────────────

def build_enriched(companies: list) -> list:
    """Convert companies list to format expected by excel exporter."""
    enriched = []
    for c in companies:
        enriched.append({
            "identity": {
                "nom": c.get("nom", "N/A"),
                "siren": c.get("siren", "N/A"),
                "siret": c.get("siret", "N/A"),
                "naf": c.get("naf", "N/A"),
                "naf_label": "N/A",
                "ceo": c.get("ceo", "N/A"),
                "address": c.get("address", "N/A"),
                "website": c.get("website", "N/A"),
                "status": "found",
            },
            "phones": c.get("phones", []),
        })
    return enriched


# ── Main pipeline ─────────────────────────────────────────────────────────────

def discover_and_process(
    naf_code: str,
    postal_codes: list,
    target: int = 500,
    output_path: str = None,
    job: dict = None,
) -> str:

    if job:
        job["status"] = "running"
        job["stage"] = "discovery"

    # Step 1: Discover
    companies = discover_companies(naf_code, postal_codes, target)

    if job:
        job["discovered"] = len(companies)
        job["total"] = len(companies)
        job["stage"] = "enrichment"

    # Step 2: Get phones from Maps
    companies = batch_maps_phones(companies, job=job)

    # Step 3: Export
    enriched = build_enriched(companies)
    path = export_to_excel(enriched, output_path)

    with_phone = sum(1 for c in companies if c.get("phones"))
    logger.info(f"✅ Done: {len(companies)} leads | {with_phone} with phone → {path}")

    if job:
        job["status"] = "done"
        job["file"] = path
        job["final_count"] = len(companies)
        job["with_phone"] = with_phone

    return path


def process_leads(leads: list, output_path: str = None) -> str:
    """Manual/CSV input pipeline — no Maps scraping."""
    from scraper.identity import get_company_identity
    from scraper.dm_hunter import hunt_dm_phones

    enriched = []
    for i, lead in enumerate(leads, 1):
        name = lead.get("name", "").strip()
        city = lead.get("city", "").strip()
        logger.info(f"[{i}/{len(leads)}] {name}")
        identity = get_company_identity(name=name, city=city)
        phones = hunt_dm_phones(
            company=identity.get("nom", name),
            ceo=identity.get("ceo", "N/A"),
            city=city,
            website=identity.get("website", "N/A"),
        )
        enriched.append({"identity": identity, "phones": phones})
        if i < len(leads):
            time.sleep(2)

    path = export_to_excel(enriched, output_path)
    logger.info(f"✅ Excel saved: {path}")
    return path


# ── Test ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    discover_and_process(
        naf_code="43.22A",
        postal_codes=["13001", "13002", "13003"],
        target=5,
    )