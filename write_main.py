code = '''import time
import threading
import os
import requests
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

state = {"running": False, "progress": 0, "total": 0, "log": [], "results": [], "done": False, "error": None}

INTENT_KEYWORDS = [
    "appel d offres energie", "changement fournisseur", "renegociation contrat",
    "offre electricite", "offre gaz", "marche energie", "fournisseur alternatif",
    "economies energie entreprise", "contrat gaz professionnel", "contrat electricite pro",
    "mise en concurrence energie", "renouvellement contrat energie"
]

def get_company_details_insee(company_name, city):
    try:
        url = "https://api.insee.fr/api-sirene/3.11/siret"
        headers = {"Accept": "application/json"}
        q = f'denominationUniteLegale:"{company_name}"'
        params = {"q": q, "nombre": 1, "champs": "siret,siren,activitePrincipaleUniteLegale,denominationUniteLegale,nomUniteLegale,prenomUsuelUniteLegale"}
        resp = requests.get(url, headers=headers, params=params, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            etablissements = data.get("etablissements", [])
            if etablissements:
                e = etablissements[0]
                ul = e.get("uniteLegale", {})
                return {
                    "SIREN": e.get("siren", "N/A"),
                    "SIRET": e.get("siret", "N/A"),
                    "Code NAF": ul.get("activitePrincipaleUniteLegale", "N/A"),
                    "CEO / Dirigeant": f"{ul.get('prenomUsuelUniteLegale', '')} {ul.get('nomUniteLegale', '')}".strip() or "N/A",
                }
    except Exception as ex:
        pass

    # Fallback: try recherche entreprises API (no token needed)
    try:
        url2 = "https://recherche-entreprises.api.gouv.fr/search"
        params2 = {"q": company_name, "per_page": 1}
        resp2 = requests.get(url2, params=params2, timeout=8)
        if resp2.status_code == 200:
            data2 = resp2.json()
            results = data2.get("results", [])
            if results:
                r = results[0]
                dirigeants = r.get("dirigeants", [])
                ceo = ""
                if dirigeants:
                    d = dirigeants[0]
                    ceo = f"{d.get('prenoms', '')} {d.get('nom', '')}".strip()
                siege = r.get("siege", {})
                return {
                    "SIREN": r.get("siren", "N/A"),
                    "SIRET": siege.get("siret", "N/A"),
                    "Code NAF": r.get("activite_principale", "N/A"),
                    "CEO / Dirigeant": ceo or "N/A",
                }
    except Exception:
        pass

    return {"SIREN": "N/A", "SIRET": "N/A", "Code NAF": "N/A", "CEO / Dirigeant": "N/A"}


def detect_intent_signals(driver):
    signals = []
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        for kw in INTENT_KEYWORDS:
            if kw in page_text:
                signals.append(kw)
    except Exception:
        pass
    return ", ".join(signals) if signals else "No signal detected"


def run_scraper(sector, region, target, zones):
    global state
    state.update({"running": True, "progress": 0, "total": target, "log": [], "results": [], "done": False, "error": None})

    options = webdriver.ChromeOptions()
    options.add_argument("--lang=fr")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(r"C:\\Users\\Admin\\Desktop\\Lead-Scraper\\chromedriver.exe"), options=options)

    collected = []
    seen_links = set()

    def log(msg):
        state["log"].append(msg)
        print(msg)

    try:
        for zone in zones:
            if len(collected) >= target:
                break
            search_query = f"{sector} {zone}"
            log(f"Scanning: {search_query} ({len(collected)}/{target})")
            driver.get(f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}")
            time.sleep(5)
            try:
                driver.find_element(By.XPATH, \'//button[contains(@aria-label,"Tout accepter") or contains(.,"Accepter")]\').click()
                time.sleep(2)
            except Exception:
                pass
            for _ in range(15):
                try:
                    panel = driver.find_element(By.XPATH, \'//div[@role="feed"]\')
                    driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", panel)
                    time.sleep(1.5)
                except Exception:
                    try:
                        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
                        time.sleep(1.5)
                    except Exception:
                        pass
            links = [e.get_attribute("href") for e in driver.find_elements(By.XPATH, \'//a[contains(@href,"/maps/place/")]\')]
            new_links = [l for l in links if l and l not in seen_links]
            log(f"   -> {len(new_links)} new listings found")
            for link in new_links:
                if len(collected) >= target:
                    break
                try:
                    seen_links.add(link)
                    driver.get(link)
                    time.sleep(2.5)
                    try:
                        name = driver.find_element(By.XPATH, "//h1").text
                    except Exception:
                        name = "N/A"
                    try:
                        phone = driver.find_element(By.XPATH, \'//button[contains(@data-item-id,"phone:tel:")]\').get_attribute("data-item-id").replace("phone:tel:", "").strip()
                    except Exception:
                        phone = "N/A"
                    try:
                        address = driver.find_element(By.XPATH, \'//button[@data-item-id="address"]\').text
                    except Exception:
                        address = "N/A"
                    try:
                        website = driver.find_element(By.XPATH, \'//a[@data-item-id="authority"]\').get_attribute("href")
                    except Exception:
                        website = "N/A"
                    try:
                        category = driver.find_element(By.XPATH, \'//button[contains(@jsaction,"category")]\').text
                    except Exception:
                        category = "N/A"
                    if phone == "N/A":
                        continue
                    city_from_address = address.split(",")[-1].strip() if address != "N/A" else region
                    company_data = get_company_details_insee(name, city_from_address)
                    intent = detect_intent_signals(driver)
                    entry = {
                        "Nom": name,
                        "Telephone": phone,
                        "Adresse": address,
                        "Site Web": website,
                        "Categorie": category,
                        "SIREN": company_data["SIREN"],
                        "SIRET": company_data["SIRET"],
                        "Code NAF": company_data["Code NAF"],
                        "CEO Dirigeant": company_data["CEO / Dirigeant"],
                        "Signaux Energie": intent,
                        "Zone": zone,
                    }
                    collected.append(entry)
                    state["results"] = collected.copy()
                    state["progress"] = len(collected)
                    log(f"   OK [{len(collected)}/{target}] {name} | {phone} | SIRET: {company_data['SIRET']}")
                except Exception as e:
                    log(f"   Error: {str(e)[:80]}")
                    continue
    except Exception as e:
        state["error"] = str(e)
        log(f"Fatal error: {e}")
    finally:
        driver.quit()
        state["running"] = False
        state["done"] = True
        log(f"Done. {len(collected)} leads collected.")
        if collected:
            pd.DataFrame(collected).to_excel("leads_export.xlsx", index=False)
            log("leads_export.xlsx saved.")


class ScrapeRequest(BaseModel):
    sector: str
    region: str
    target: int
    zones: list[str]


@app.post("/start")
def start_scrape(req: ScrapeRequest):
    if state["running"]:
        return {"error": "Scraper already running"}
    threading.Thread(target=run_scraper, args=(req.sector, req.region, req.target, req.zones), daemon=True).start()
    return {"status": "started"}


@app.get("/status")
def get_status():
    return {"running": state["running"], "progress": state["progress"], "total": state["total"], "done": state["done"], "log": state["log"][-20:], "count": len(state["results"]), "error": state["error"]}


@app.get("/results")
def get_results():
    return {"results": state["results"]}


@app.get("/export")
def export_excel():
    path = "leads_export.xlsx"
    if os.path.exists(path):
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="leads_export.xlsx")
    return {"error": "No export file found yet"}


@app.post("/stop")
def stop_scraper():
    state["running"] = False
    return {"status": "stop requested"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''

with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)

print("main.py created successfully!")