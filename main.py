"""
main.py — B2B Lead Scraper Full Pipeline
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
    enriched = []
    total = len(leads)
    for i, lead in enumerate(leads, 1):
        name = lead.get("name", "").strip()
        city = lead.get("city", "").strip()
        logger.info(f"[{i}/{total}] {name}")
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
    logger.info(f"✅ Excel saved: {path}")
    return path


def discover_and_process(
    naf_code: str,
    postal_codes: list,
    target: int = 500,
    output_path: str = None,
    job: dict = None,
) -> str:
    # Step 1 — Discovery
    if job:
        job["stage"] = "discovery"
        job["status"] = "running"

    discovered = discover_companies(
        naf_code=naf_code,
        postal_codes=postal_codes,
        target=target,
    )

    if job:
        job["discovered"] = len(discovered)
        job["stage"] = "enrichment"
        job["total"] = len(discovered)
        job["progress"] = 0
        job["with_phone"] = 0

    # Step 2 — Enrich
    enriched = []
    for i, lead in enumerate(discovered, 1):
        name = lead.get("name", "").strip()
        city = lead.get("city", "").strip()

        logger.info(f"[{i}/{len(discovered)}] Enriching: {name}")

        if job:
            job["progress"] = i
            job["current"] = name

        identity = get_company_identity(name=name, city=city)
        phones = hunt_dm_phones(
            company=identity.get("nom", name),
            ceo=identity.get("ceo", "N/A"),
            city=city,
            website=identity.get("website", "N/A"),
        )

        enriched.append({"identity": identity, "phones": phones})

        if phones and job:
            job["with_phone"] = sum(1 for e in enriched if e["phones"])

        if i < len(discovered):
            time.sleep(2)

    # Step 3 — Export ALL leads
    path = export_to_excel(enriched, output_path)

    with_phone = sum(1 for e in enriched if e["phones"])
    logger.info(f"✅ {len(enriched)} leads exported | {with_phone} with phone")

    if job:
        job["status"] = "done"
        job["file"] = path
        job["final_count"] = len(enriched)
        job["with_phone"] = with_phone

    return path


if __name__ == "__main__":
    discover_and_process(
        naf_code="56.10A",
        postal_codes=["75001", "75002", "75003"],
        target=3,
    )