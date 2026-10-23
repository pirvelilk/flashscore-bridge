def find_flashscore_event_id(home_team, away_team):
    print(f"[FS] Searching for: {home_team} vs {away_team}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.flashscore.com",
        "Referer": "https://www.flashscore.com/"
    }

    # ვასუფთავებთ სახელებს ზედმეტი პრეფიქსებისგან (FC, CF, FK...)
    def clean_name(n):
        n = re.sub(r"\b(fc|cf|fk|sc|ac|cd|as|afc|club)\b", "", n, flags=re.IGNORECASE)
        return n.strip()

    h_name = clean_name(home_team)
    a_name = clean_name(away_team)

    search_terms = [h_name, a_name, home_team.split()[0], away_team.split()[0]]
    
    for term in search_terms:
        if not term or len(term) < 3:
            continue
        try:
            url = f"https://search.flashscore.com/search/all?q={term}&l=1"
            res = requests.get(url, headers=headers, timeout=6)
            print(f"[FS SEARCH] Term: '{term}' -> Status: {res.status_code}")
            if res.status_code == 200:
                data = res.json()
                for item in data.get("results", []):
                    if item.get("type") == "event":
                        p1 = item.get("participant1_name", "").lower()
                        p2 = item.get("participant2_name", "").lower()
                        
                        # შემოწმება ნაწილობრივ დამთხვევაზე
                        h_low = h_name.lower()
                        a_low = a_name.lower()
                        
                        if (h_low in p1 or p1 in h_low or h_low in p2) and (a_low in p2 or p2 in a_low or a_low in p1):
                            event_id = item.get("id")
                            print(f"[FS SUCCESS] Found Event ID: {event_id}")
                            return event_id
        except Exception as e:
            print(f"[FS SEARCH EXCEPTION] {e}")

    print(f"[FS FAILED] ID not found for {home_team} vs {away_team}")
    return None


def toggle_flashscore_favorite(fs_event_id, add=True):
    if not fs_event_id:
        return False
        
    url = "https://lsid.eu/v3/storemergeddata"
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://www.flashscore.com",
        "referer": "https://www.flashscore.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    key_name = f"mygames.data.g_1_{fs_event_id}"
    now_ts = int(time.time())
    if add:
        diff = {"merge": {"AD": now_ts, "MG": "0", "is_duel": 1}, "unmerge": []}
    else:
        diff = {"merge": {}, "unmerge": ["AD", "MG", "is_duel"]}

    payload = {
        "loggedIn": FLASHSCORE_AUTH,
        "key": key_name,
        "dataDiff": diff,
        "project": 2
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=6)
        print(f"[FS SYNC] Event: {fs_event_id} | Add: {add} | Status: {res.status_code}")
        return res.status_code == 200
    except Exception as e:
        print(f"[FS SYNC ERROR] {e}")
        return False
