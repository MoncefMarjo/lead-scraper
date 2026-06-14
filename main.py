"""
main.py
B2B Lead Scraper — Full Pipeline
Step 1: Identity resolution (gouvernement API)
Step 2: Decision-maker phone hunting (Google, Website, LinkedIn)
Step 3: Excel export with confidence scores
"""

import time
import logging
from scraper.identity import get_company_identity
from scraper.dm_hunter import hunt_dm_phones
from export.excel import export_to_excel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def process_leads(leads: list, output_path: str = None) -> str:
    """
    Full pipeline: identity → phone hunt → Excel export.

    Args:
        leads: list of dicts with keys: name, city (opt), sector (opt)
        output_path: optional Excel output path

    Returns:
        Path of the created Excel file
    """
    enriched = []
    total = len(leads)

    for i, lead in enumerate(leads, 1):
        name   = lead.get("name", "").strip()
        city   = lead.get("city", "").strip()

        logger.info(f"\n{'='*50}")
        logger.info(f"Processing lead {i}/{total}: {name}")
        logger.info(f"{'='*50}")

        # ── Step 1: Identity ──────────────────────────────
        identity = get_company_identity(name=name, city=city)

        # ── Step 2: Phone Hunt ────────────────────────────
        phones = hunt_dm_phones(
            company=identity.get("nom", name),
            ceo=identity.get("ceo", "N/A"),
            city=city,
            website=identity.get("website", "N/A"),
        )

        enriched.append({
            "identity": identity,
            "phones": phones,
        })

        # Polite delay between leads
        if i < total:
            logger.info("Waiting before next lead...")
            time.sleep(3)

    # ── Step 3: Excel Export ──────────────────────────────
    path = export_to_excel(enriched, output_path)
    logger.info(f"\n✅ Done! {total} leads exported to: {path}")
    return path


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # ── Edit your leads here ──────────────────────────────
    leads = [
        {"name": "Kandbaz",    "city": "Paris"},
        {"name": "Doctolib",   "city": "Paris"},
        {"name": "Blablacar",  "city": "Paris"},
    ]
    # ─────────────────────────────────────────────────────

    output = process_leads(leads)
    print(f"\n📊 Excel file ready: {output}")