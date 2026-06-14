from scraper.dm_hunter import hunt_dm_phones

print("\n=== TEST KANDBAZ ===\n")
phones = hunt_dm_phones(
    company="Kandbaz",
    ceo="N/A",
    city="Paris",
    website="https://www.kandbaz.com"
)

if phones:
    for p in phones:
        print(f"📞 {p['phone']} | {p['type']} | {p['confidence']}% | {p['sources']}")
else:
    print("No phones found.")