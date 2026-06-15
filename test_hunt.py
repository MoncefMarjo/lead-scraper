from scraper.discovery import discover_companies
from scraper.identity import get_company_identity
from scraper.dm_hunter import hunt_dm_phones
from export.excel import export_to_excel

leads = discover_companies('56.10A', ['75001'], target=2)
enriched = []
for l in leads:
    identity = get_company_identity(l['name'], l['city'])
    phones = hunt_dm_phones(identity['nom'], identity['ceo'], l['city'], identity['website'])
    print('Company:', identity['nom'], '| Phones:', len(phones))
    enriched.append({'identity': identity, 'phones': phones})

path = export_to_excel(enriched, 'debug_test.xlsx')
print('Excel saved:', path)