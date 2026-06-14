"""
identity.py
Step 1 — Company identity resolution via recherche-entreprises.api.gouv.fr
Returns: SIREN, SIRET, NAF, CEO name, address, website URL
"""

import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "https://recherche-entreprises.api.gouv.fr/search"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_ceo(dirigeants: list) -> str:
    """Pick the most relevant decision-maker from the dirigeants list."""
    priority_roles = ["gérant", "président", "directeur général", "pdg", "ceo", "administrateur"]
    if not dirigeants:
        return "N/A"
    # Only consider physical persons (not companies)
    physical = [d for d in dirigeants if d.get("type_dirigeant") == "personne physique"]
    if not physical:
        return "N/A"
    # Try to find priority role first
    for d in physical:
        role = d.get("qualite", "").lower()
        if any(p in role for p in priority_roles):
            prenom = d.get("prenom", "").strip().title()
            nom = d.get("nom", "").strip().upper()
            # Clean duplicate like "PUTHET (PUTHET)"
            full = f"{prenom} {nom}".strip()
            if "(" in full:
                full = full.split("(")[0].strip()
            return full or "N/A"
    # Fallback: first physical person
    d = physical[0]
    prenom = d.get("prenom", "").strip().title()
    nom = d.get("nom", "").strip().upper()
    full = f"{prenom} {nom}".strip()
    if "(" in full:
        full = full.split("(")[0].strip()
    return full or "N/A"


def _extract_address(siege: dict) -> str:
    """Use the clean pre-built adresse field directly."""
    return siege.get("adresse", "").strip() or "N/A"


def _extract_website(siege: dict) -> str:
    """Extract website URL if available."""
    url = siege.get("site_internet", "") or ""
    if url and not url.startswith("http"):
        url = "https://" + url
    return url.strip() or "N/A"


# ── Main Function ─────────────────────────────────────────────────────────────

def get_company_identity(name: str, city: str = "", sector: str = "") -> dict:
    """
    Query the govt API to resolve company identity.

    Args:
        name:   Company name (required)
        city:   City hint to narrow results (optional)
        sector: Activity sector hint (optional)

    Returns:
        dict with keys:
            nom, siren, siret, naf, naf_label,
            ceo, address, website, raw_score, status
    """

    empty = {
        "nom": name,
        "siren": "N/A",
        "siret": "N/A",
        "naf": "N/A",
        "naf_label": "N/A",
        "ceo": "N/A",
        "address": "N/A",
        "website": "N/A",
        "raw_score": 0,
        "status": "not_found",
    }

    if not name or not name.strip():
        logger.warning("get_company_identity called with empty name")
        empty["status"] = "empty_name"
        return empty

    # Build query — combine name + city for better precision
    query = name.strip()
    if city:
        query += f" {city.strip()}"

    params = {
        "q": query,
        "page": 1,
        "per_page": 5,  # Get top 5, pick best match
    }

    try:
        logger.info(f"Querying API for: '{query}'")
        resp = requests.get(API_BASE, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            logger.warning(f"No results found for '{query}'")
            empty["status"] = "not_found"
            return empty

        # Pick the first (highest scored) result
        company = results[0]
        siege = company.get("siege", {})
        dirigeants = company.get("dirigeants", [])
        matching = company.get("matching_etablissements", [{}])

        # Extract fields
        nom = company.get("nom_raison_sociale", name).strip()
        siren = company.get("siren", "N/A")
        siret = siege.get("siret", "N/A")
        naf = siege.get("activite_principale", "N/A")
        naf_label = company.get("libelle_activite_principale", {})
        if isinstance(naf_label, dict):
            naf_label = naf_label.get("fr", "N/A")
        elif not naf_label:
            naf_label = "N/A"

        ceo = _extract_ceo(dirigeants)
        address = _extract_address(siege)
        website = _extract_website(siege)

        result = {
            "nom": nom,
            "siren": siren,
            "siret": siret,
            "naf": naf,
            "naf_label": naf_label,
            "ceo": ceo,
            "address": address,
            "website": website,
            "raw_score": company.get("score", 0),
            "status": "found",
        }

        logger.info(f"✅ Found: {nom} | SIREN: {siren} | CEO: {ceo}")
        return result

    except requests.exceptions.Timeout:
        logger.error(f"Timeout querying API for '{query}'")
        empty["status"] = "timeout"
        return empty
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed for '{query}': {e}")
        empty["status"] = "api_error"
        return empty
    except Exception as e:
        logger.error(f"Unexpected error for '{query}': {e}")
        empty["status"] = "error"
        return empty


# ── Batch Function ────────────────────────────────────────────────────────────

def get_companies_identity(leads: list, delay: float = 1.0) -> list:
    """
    Process a list of leads through identity resolution.

    Args:
        leads: list of dicts with keys: name, city (opt), sector (opt)
        delay: seconds between API calls (be polite to the API)

    Returns:
        list of identity dicts
    """
    results = []
    total = len(leads)

    for i, lead in enumerate(leads, 1):
        logger.info(f"Processing lead {i}/{total}: {lead.get('name', '?')}")
        identity = get_company_identity(
            name=lead.get("name", ""),
            city=lead.get("city", ""),
            sector=lead.get("sector", ""),
        )
        results.append(identity)

        if i < total:
            time.sleep(delay)  # Polite delay between requests

    return results


# ── Quick Test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_leads = [
        {"name": "Kandbaz", "city": "Paris"},
        {"name": "BNP Paribas", "city": "Paris"},
        {"name": "Boulangerie Dupont", "city": "Lyon"},
    ]

    print("\n=== IDENTITY RESOLUTION TEST ===\n")
    results = get_companies_identity(test_leads, delay=1.0)

    for r in results:
        print(f"""
Company : {r['nom']}
SIREN   : {r['siren']}
SIRET   : {r['siret']}
NAF     : {r['naf']} — {r['naf_label']}
CEO     : {r['ceo']}
Address : {r['address']}
Website : {r['website']}
Status  : {r['status']}
{'─'*40}""")