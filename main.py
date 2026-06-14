"""
main.py
B2B Lead Scraper — Full Pipeline
"""

import time
import logging
from scraper.identity import get_company_identity
from scraper.dm_hunter import hunt_dm_phones
from scraper.discovery import discover_companies
from export.excel import export_to_excel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def process_leads(leads: list, output_path: str = None) -> str:
    """
    Enrich a list of leads: identity + phone hunt + Excel export.
    """
    enriched = []
    total = len(leads)

    for i, lead in enumerate(leads, 1):
        name = lead.get("name", "").strip()
        city = lead.get("city", "").strip()

        logger.info(f"\n{'='*50}")
        logger.info(f"Processing lead {i}/{total}: {name}")
        logger.info(f"{'='*50}")

        identity = get_company_identity(name=name, city=city)
        phones = hunt_dm_phones(
            company=identity.get("nom", name),
            ceo=identity.get("ceo", "N/A"),
            city=city,
            website=identity.get("website", "N/A"),
        )

        enriched.append({"identity": identity, "phones": phones})

        if i < total:
            time.sleep(3)

    path = export_to_excel(enriched, output_path)
    logger.info(f"\n✅ Done! {total} leads exported to: {path}")
    return path


def discover_and_process(
    naf_code: str,
    postal_codes: list,
    target: int = 500,
    output_path: str = None,
    job: dict = None,
) -> str:
    """
    Full auto pipeline:
    1. Discover companies via SIRENE API
    2. Enrich each with identity + phone
    3. Keep only leads WITH a phone
    4. Export to Excel
    """
    # Step 1 — Discovery
    logger.info(f"🔍 Discovering companies — NAF: {naf_code} | Target: {target}")
    if job:
        job["stage"] = "discovery"
        job["status"] = "running"

    discovered = discover_companies(
        naf_code=naf_code,
        postal_codes=postal_codes,
        target=target,
    )

    logger.info(f"✅ Discovered {len(discovered)} companies")
    if job:
        job["discovered"] = len(discovered)
        job["stage"] = "enrichment"

    # Step 2 — Enrich each company
    enriched = []
    for i, lead in enumerate(discovered, 1):
        name = lead.get("name", "").strip()
        city = lead.get("city", "").strip()

        logger.info(f"\n[{i}/{len(discovered)}] Enriching: {name}")
        if job:
            job["progress"] = i
            job["total"] = len(discovered)
            job["current"] = name

        identity = get_company_identity(name=name, city=city)
        phones = hunt_dm_phones(
            company=identity.get("nom", name),
            ceo=identity.get("ceo", "N/A"),
            city=city,
            website=identity.get("website", "N/A"),
        )

        # Step 3 — Include ALL leads, phone or not
        enriched.append({"identity": identity, "phones": phones})
        if job:
            job["enriched"] = len(enriched)

        if phones:
            logger.info(f"✅ Phone found: {phones[0]['phone']} ({phones[0]['confidence']}%)")
            if job:
                job["with_phone"] = len([e for e in enriched if e["phones"]])
        else:
            logger.info(f"⚠️ No phone found — included with empty phone")

        if i < len(discovered):
            time.sleep(2)

    with_phone = len([e for e in enriched if e["phones"]])
    logger.info(f"\n📊 {len(enriched)} total leads | {with_phone} with phone")

    # Step 4 — Export
    path = export_to_excel(enriched, output_path)
    logger.info(f"✅ Excel saved: {path}")
    if job:
        job["status"] = "done"
        job["file"] = path
        job["final_count"] = len(enriched)

    return path


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    discover_and_process(
        naf_code="45.20A",
        postal_codes=["75001", "75002", "75003", "75004", "75005"],
        target=10,
    )