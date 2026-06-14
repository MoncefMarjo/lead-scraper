"""
discovery.py
Step 0 — Company discovery via SIRENE API
Finds active companies by NAF code + postal codes
Returns a list of leads ready for the enrichment pipeline
"""

import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "https://recherche-entreprises.api.gouv.fr/search"


# ── Main Discovery Function ───────────────────────────────────────────────────

def discover_companies(
    naf_code: str,
    postal_codes: list,
    target: int = 500,
    per_page: int = 25,
) -> list:
    """
    Discover active companies by NAF code across multiple postal codes.

    Args:
        naf_code:     NAF/APE activity code (ex: '4520A')
        postal_codes: List of postal codes to search (ex: ['13001', '13002'])
        target:       Max number of unique companies to return
        per_page:     Results per API call (max 25)

    Returns:
        List of lead dicts with: name, city, siren, siret, address
    """

    seen_sirets = set()
    leads = []
    index = 0

    logger.info(f"🔍 Starting discovery — NAF: {naf_code} | Target: {target} leads")
    logger.info(f"📮 Postal codes: {postal_codes}")

    # Loop through postal codes until target is reached
    cycles = 0
    while len(leads) < target:

        if index >= len(postal_codes):
            cycles += 1
            if cycles >= 3:
                logger.warning("⚠️ Cycled through all postal codes 3 times — stopping.")
                break
            logger.info("🔄 Restarting postal code cycle...")
            index = 0

        cp = postal_codes[index]
        page = 1

        while len(leads) < target:
            params = {
                "activite_principale": naf_code,
                "code_postal": cp,
                "per_page": per_page,
                "page": page,
            }

            try:
                resp = requests.get(
                    API_BASE,
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])

                if not results:
                    break  # No more results for this postal code

                for company in results:
                    if len(leads) >= target:
                        break

                    siren = company.get("siren", "N/A")
                    nom = company.get("nom_complet", "").split("(")[0].strip()
                    nom_simple = company.get("nom_raison_sociale", nom).strip()

                    etablissements = company.get("matching_etablissements", [])
                    siege = company.get("siege", {})

                    siret = siege.get("siret", "N/A")
                    adresse = siege.get("adresse", "N/A")
                    ville = siege.get("libelle_commune", "")
                    cp_found = siege.get("code_postal", cp)

                    # Skip duplicates
                    if siret in seen_sirets or siret == "N/A":
                        continue

                    seen_sirets.add(siret)
                    leads.append({
                        "name": nom_simple,
                        "city": ville or cp_found,
                        "siren": siren,
                        "siret": siret,
                        "address": adresse,
                        "naf": naf_code,
                    })

                    logger.info(f"[{len(leads)}/{target}] Found: {nom_simple} — {ville}")

                # Check if there are more pages
                total = data.get("total_results", 0)
                if page * per_page >= total:
                    break  # No more pages for this postal code

                page += 1
                time.sleep(0.5)  # Polite delay

            except requests.exceptions.RequestException as e:
                logger.warning(f"API error for postal code {cp}: {e}")
                break

        index += 1
        time.sleep(0.3)

    logger.info(f"✅ Discovery complete — {len(leads)} companies found")
    return leads


# ── Quick Test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = discover_companies(
        naf_code="45.20A",
        postal_codes=["75001", "75002", "75003"],
        target=10,
    )

    print(f"\n=== DISCOVERY TEST — {len(results)} companies ===\n")
    for r in results:
        print(f"  {r['name']} | {r['city']} | SIRET: {r['siret']}")