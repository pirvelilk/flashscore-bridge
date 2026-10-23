import requests
import re
import time
import html
from datetime import datetime, timezone, timedelta

API_KEY = "a126d8e18f59628441ad42887c238103"
TELEGRAM_BOT_TOKEN = "8861991818:AAGpvRwffowT-1csmJIjqioJ-BWsphjT4O0"
ALLOWED_CHAT_ID = 6179352546

FLASHSCORE_AUTH = {
    "id": "638d0025a15efa96a54d5491",
    "hash": "c1fe37406260766f6367dff91934a712217a4391"
}

BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

FLAG_DICT = {
    "world": "🌐", "international": "🌐", "spain": "🇪🇸", "brazil": "🇧🇷",
    "colombia": "🇨🇴", "estonia": "🇪🇪", "china": "🇨🇳", "uzbekistan": "🇺🇿",
    "south korea": "🇰🇷", "korea": "🇰🇷", "japan": "🇯🇵", "saudi arabia": "🇸🇦",
    "qatar": "🇶🇦", "united arab emirates": "🇦🇪", "uae": "🇦🇪", "oman": "🇴🇲",
    "germany": "🇩🇪", "england": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "italy": "🇮🇹", "france": "🇫🇷",
    "portugal": "🇵🇹", "argentina": "🇦🇷", "finland": "🇫🇮", "paraguay": "🇵🇾",
    "georgia": "🇬🇪", "bolivia": "🇧🇴", "albania": "🇦🇱", "wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "serbia": "🇷🇸",
    "australia": "🇦🇺", "malaysia": "🇲🇾", "uruguay": "🇺🇾", "mexico": "🇲🇽",
    "chile": "🇨🇱", "peru": "🇵🇪", "ecuador": "🇪🇨", "venezuela": "🇻🇪"
}

def get_country_display(country_name):
    if not country_name:
        return ""
    flag = FLAG_DICT.get(country_name.strip().lower(), "🌐")
    return f"{country_name} {flag}"

ORIGINAL_MESSAGES = {}
REMINDERS = {}
LAST_REMINDER_CHECK = 0
IS_CANCELLED = False
FLASHSCORE_CACHE = {}

DEFAULT_KEYBOARD = {
    "keyboard": [
        [{"text": "📅 დღევანდელი დარჩენილი"}, {"text": "⏭ ხვალინდელი თამაშები"}],
        [{"text": "🗓 ზეგინდელი თამაშები"}, {"text": "🛑 სდექ"}]
    ],
    "resize_keyboard": True
}

STAGE_GEO = {
    "Round of 16": "1/8 ფინალი",
    "8th Finals": "1/8 ფინალი",
    "Quarter-finals": "მეოთხედფინალი",
    "Semi-finals": "ნახევარფინალი",
    "Final": "ფინალი",
    "Finals": "ფინალი"
}

def get_tbilisi_time():
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=4)

def send_telegram(chat_id, text, reply_markup=None):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    for _ in range(3):
        try:
            res = requests.post(url, json=payload, timeout=8).json()
            if res.get("ok"):
                return res.get("result", {}).get("message_id")
            elif res.get("error_code") == 429:
                retry_after = res.get("parameters", {}).get("retry_after", 2)
                time.sleep(retry_after + 1)
            else:
                payload.pop("parse_mode", None)
                res2 = requests.post(url, json=payload, timeout=8).json()
                return res2.get("result", {}).get("message_id")
        except Exception:
            time.sleep(1)
    return None

def edit_message_text_and_markup(chat_id, message_id, text, reply_markup):
    url = f"{TELEGRAM_API_URL}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": reply_markup
    }
    try:
        requests.post(url, json=payload, timeout=6)
    except Exception:
        pass

def answer_callback_query(callback_query_id, text=None):
    url = f"{TELEGRAM_API_URL}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        requests.post(url, json=payload, timeout=4)
    except Exception:
        pass

def load_flashscore_feed_for_day(days_offset=0):
    """Flashscore-ის Feed-იდან დღის მატჩების ID-ების ჩატვირთვა"""
    global FLASHSCORE_CACHE
    url = f"https://local-global.flashscore.ninja/2/x/feed/f_1_{days_offset}_3_en_1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "x-fsign": "SW9D1eZo"
    }
    try:
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            raw_data = r.text
            blocks = raw_data.split("~AA÷")
            for b in blocks[1:]:
                parts = b.split("¬")
                data_dict = {}
                for p in parts:
                    if "÷" in p:
                        k, v = p.split("÷", 1)
                        data_dict[k] = v
                event_id = b.split("¬")[0]
                home = data_dict.get("AE", "").lower()
                away = data_dict.get("AF", "").lower()
                if event_id and home and away:
                    FLASHSCORE_CACHE[f"{home}_{away}"] = event_id
            print(f"[FS FEED] Cached {len(FLASHSCORE_CACHE)} matches for offset {days_offset}")
    except Exception as e:
        print(f"[FS FEED ERROR] {e}")

def find_flashscore_event_id(home_team, away_team):
    """მოძიება Flashscore Cache-ში და საძიებო fallback"""
    h_clean = re.sub(r"\b(fc|cf|fk|sc|ac|cd|as|afc|club|u20|u19)\b", "", home_team, flags=re.IGNORECASE).strip().lower()
    a_clean = re.sub(r"\b(fc|cf|fk|sc|ac|cd|as|afc|club|u20|u19)\b", "", away_team, flags=re.IGNORECASE).strip().lower()

    # 1. ვეძებთ ლოკალურ Cache-ში
    for key, eid in FLASHSCORE_CACHE.items():
        if (h_clean in key or key.startswith(h_clean[:4])) and (a_clean in key or a_clean[:4] in key):
            print(f"[FS CACHE HIT] Found Event ID: {eid} for {home_team} vs {away_team}")
            return eid

    # 2. Fallback საძიებო მოთხოვნა
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }
    terms = [h_clean, a_clean, home_team.split()[0]]
    for t in terms:
        if not t or len(t) < 3:
            continue
        try:
            url = f"https://search.flashscore.com/search/all?q={t}&l=1"
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                for item in res.json().get("results", []):
                    if item.get("type") == "event":
                        p1 = item.get("participant1_name", "").lower()
                        p2 = item.get("participant2_name", "").lower()
                        if (h_clean in p1 or p1 in h_clean) and (a_clean in p2 or p2 in a_clean):
                            return item.get("id")
        except Exception:
            pass
            
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

def get_match_odds(fixture_id):
    try:
        url_odds = f"{BASE_URL}/odds"
        p = {"fixture": fixture_id}
        res = requests.get(url_odds, headers=HEADERS, params=p, timeout=4).json()
        data = res.get("response", [])
        if data and data[0].get("bookmakers"):
            for b in data[0]["bookmakers"]:
                for bet in b.get("bets", []):
                    if bet.get("id") == 1 or bet.get("name") == "Match Winner":
                        values = {v["value"]: v["odd"] for v in bet.get("values", [])}
                        home_odd = values.get("Home", "-")
                        draw_odd = values.get("Draw", "-")
                        away_odd = values.get("Away", "-")
                        return f"1: <b>{home_odd}</b> | X: <b>{draw_odd}</b> | 2: <b>{away_odd}</b>"
    except Exception:
        pass
    return "არ მოიძებნა"

def is_cup_stage_match(fixture):
    league_name = fixture.get("league", {}).get("name", "")
    country_name = fixture.get("league", {}).get("country", "")
    round_name = fixture.get("league", {}).get("round", "")
    home_name = fixture.get("teams", {}).get("home", {}).get("name", "")
    away_name = fixture.get("teams", {}).get("away", {}).get("name", "")

    exclude_patterns = [
        r"\bwomen\b", r"\bfemmes\b", r"\bfrauen\b", r"\bdonne\b", 
        r"\bfeminina\b", r"\bfemenil\b", r"\bwom\b", r"\(w\)",
        r"\bamateur\b", r"\bamateurs\b", r"\breserve\b", r"\breserves\b", r"\bii\b",
        r"\bu-?15\b", r"\bu-?16\b", r"\bu-?17\b", r"\bu-?18\b", r"\bu-?19\b",
        r"\byouth\b", r"\bjuniores\b", r"\bjunior\b", r"\bprimavera\b"
    ]
    check_str = f"{league_name} {country_name} {round_name} {home_name} {away_name}".lower()
    if any(re.search(pat, check_str) for pat in exclude_patterns):
        return False

    allowed_stages = [
        "round of 16", "8th finals", "round 16",
        "quarter-final", "quarter-finals", "quarter finals",
        "semi-final", "semi-finals", "semi finals",
        "final", "finals"
    ]
    
    rnd_lower = round_name.lower()
    if any(blocked in rnd_lower for blocked in ["round of 32", "round of 64", "qualification", "preliminary", "play-offs"]):
        return False

    return any(stg in rnd_lower for stg in allowed_stages)

def check_and_send_reminders():
    global LAST_REMINDER_CHECK
    now_time = time.time()
    if now_time - LAST_REMINDER_CHECK < 25:
        return
    LAST_REMINDER_CHECK = now_time

    now_tbilisi = get_tbilisi_time().replace(tzinfo=None)
    for fix_id, r in list(REMINDERS.items()):
        if r.get("sent"):
            continue
        diff_minutes = (r["kickoff_dt"] - now_tbilisi).total_seconds() / 60.0

        if 0 <= diff_minutes <= 10:
            msg = (
                f"⏰ <b>სათასო მატჩი იწყება 10 წუთში!</b>\n\n"
                f"⚽ <b>{html.escape(r['teams'])}</b>\n"
                f"🏆 <b>{html.escape(r['league'])}</b>"
            )
            send_telegram(r["chat_id"], msg, reply_markup=DEFAULT_KEYBOARD)
            r["sent"] = True
        elif diff_minutes < 0:
            REMINDERS.pop(fix_id, None)

def make_keyboard(fixture_id, status, fs_id=None):
    rev_text = "✅ განხილულია" if status == "reviewed" else "⬜ განხილვა"
    ign_text = "↩️ დაბრუნება" if status == "ignored" else "❌ არ განვიხილავ"
    
    row = [
        {"text": rev_text, "callback_data": f"cup_rev_{fixture_id}"},
        {"text": ign_text, "callback_data": f"cup_ign_{fixture_id}"}
    ]
    keyboard = [row]
    if fs_id:
        keyboard.append([{"text": "🔗 Flashscore-ზე გახსნა", "url": f"https://www.flashscore.com/match/{fs_id}/"}])
        
    return {"inline_keyboard": keyboard}

def send_cup_matches_for_date(chat_id, target_date, min_time_str):
    global IS_CANCELLED
    IS_CANCELLED = False

    # ვტვირთავთ Flashscore Feed-ს არჩეული დღისთვის
    try:
        t_dt = datetime.strptime(target_date, "%Y-%m-%d")
        now_dt = get_tbilisi_time().replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
        days_diff = (t_dt - now_dt).days
        load_flashscore_feed_for_day(days_diff)
    except Exception:
        pass

    url = f"{BASE_URL}/fixtures"
    params = {"date": target_date, "timezone": "Asia/Tbilisi"}
    try:
        res = requests.get(url, headers=HEADERS, params=params, timeout=12).json()
    except Exception as e:
        send_telegram(chat_id, f"API შეცდომა: {html.escape(str(e))}", reply_markup=DEFAULT_KEYBOARD)
        return
        
    matches = res.get("response", [])
    cup_matches = []

    for m in matches:
        kickoff = m["fixture"]["date"][11:16]
        if min_time_str and kickoff < min_time_str:
            continue

        if is_cup_stage_match(m):
            cup_matches.append(m)

    if not cup_matches:
        msg = f"📅 <b>თარიღი: {target_date} (თბილისი)</b>\n\nმერვედფინალიდან ფინალის ჩათვლით მატჩები არ მოიძებნა."
        send_telegram(chat_id, msg, reply_markup=DEFAULT_KEYBOARD)
        return

    header_text = (
        f"🏆 <b>სათასო ფილტრი (1/8-დან ფინალამდე): {target_date}</b>\n"
        f"⚽ ნაპოვნია <b>{len(cup_matches)}</b> მატჩი:\n"
    )
    send_telegram(chat_id, header_text, reply_markup=DEFAULT_KEYBOARD)

    for idx, m in enumerate(cup_matches, 1):
        if IS_CANCELLED:
            send_telegram(chat_id, "🛑 <b>გაგზავნა შეჩერებულია.</b>", reply_markup=DEFAULT_KEYBOARD)
            IS_CANCELLED = False
            return

        fixture_id = m["fixture"]["id"]
        match_date = m["fixture"]["date"]
        raw_home = m["teams"]["home"]["name"]
        raw_away = m["teams"]["away"]["name"]
        raw_league = m["league"].get("name", "")
        raw_round = m["league"].get("round", "")

        round_display = STAGE_GEO.get(raw_round, raw_round)
        kickoff = match_date[11:16]
        odds_str = get_match_odds(fixture_id)

        # ვეძებთ Flashscore ID-ს წინასწარ
        fs_id = find_flashscore_event_id(raw_home, raw_away)

        country_info = get_country_display(m['league'].get('country', ''))
        card = f"<b>#{idx} | {country_info} {html.escape(raw_league)}</b>\n"
        card += f"⚽ <b>{html.escape(raw_home)} — {html.escape(raw_away)}</b>\n"
        card += f"⏰ <b>დაწყება:</b> {kickoff} (თბილისი)\n"
        card += f"📍 <b>ეტაპი:</b> {html.escape(round_display)}\n"
        card += f"📊 <b>კოეფიციენტები:</b> {odds_str}\n"

        kb = make_keyboard(fixture_id, "none", fs_id)
        msg_id = send_telegram(chat_id, card, reply_markup=kb)
        if msg_id:
            ORIGINAL_MESSAGES[msg_id] = {
                "clean_text": card,
                "fixture_id": str(fixture_id),
                "status": "none",
                "match_date": match_date,
                "teams": f"{raw_home} — {raw_away}",
                "league": raw_league,
                "raw_home": raw_home,
                "raw_away": raw_away,
                "fs_id": fs_id
            }
        time.sleep(0.3)

    send_telegram(chat_id, "✅ სია დასრულებულია.", reply_markup=DEFAULT_KEYBOARD)

def parse_user_request(msg_text):
    text = msg_text.strip().lower()
    now_tbilisi = get_tbilisi_time()

    dot_match = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b", text)
    if dot_match:
        d, m, y = dot_match.groups()
        year = int(y) if y else now_tbilisi.year
        t_date = f"{int(year):04d}-{int(m):02d}-{int(d):02d}"
        min_time = now_tbilisi.strftime("%H:%M") if t_date == now_tbilisi.strftime("%Y-%m-%d") else None
        return t_date, min_time, t_date

    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_match:
        y, m, d = iso_match.groups()
        t_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        min_time = now_tbilisi.strftime("%H:%M") if t_date == now_tbilisi.strftime("%Y-%m-%d") else None
        return t_date, min_time, t_date

    if "ზეგ" in text:
        t_date = (now_tbilisi + timedelta(days=2)).strftime("%Y-%m-%d")
        return t_date, None, "ზეგინდელი"

    days_ahead_match = re.search(r"(\d+)\s*დღ", text)
    if days_ahead_match:
        days = int(days_ahead_match.group(1))
        t_date = (now_tbilisi + timedelta(days=days)).strftime("%Y-%m-%d")
        return t_date, None, f"{days} დღის შემდეგ ({t_date})"

    if "ხვალ" in text:
        t_date = (now_tbilisi + timedelta(days=1)).strftime("%Y-%m-%d")
        return t_date, None, "ხვალინდელი"

    t_date = now_tbilisi.strftime("%Y-%m-%d")
    current_time_str = now_tbilisi.strftime("%H:%M")
    return t_date, current_time_str, f"დღევანდელი დარჩენილი ({current_time_str}-დან)"

def run_bot():
    global IS_CANCELLED
    last_update_id = None

    while True:
        try:
            check_and_send_reminders()

            url = f"{TELEGRAM_API_URL}/getUpdates"
            params = {}
            if last_update_id:
                params["offset"] = last_update_id + 1

            resp = requests.get(url, params=params, timeout=10).json()
            updates = resp.get("result", [])

            for upd in updates:
                last_update_id = upd["update_id"]

                if "callback_query" in upd:
                    cq = upd["callback_query"]
                    cq_id = cq["id"]
                    cq_data = cq.get("data", "")
                    chat_id = cq["message"]["chat"]["id"]
                    msg_id = cq["message"]["message_id"]

                    answer_callback_query(cq_id)

                    if chat_id == ALLOWED_CHAT_ID and cq_data.startswith("cup_"):
                        _, action, fix_id = cq_data.split("_")
                        msg_meta = ORIGINAL_MESSAGES.get(msg_id)

                        if msg_meta:
                            current_status = msg_meta["status"]
                            clean_text = msg_meta["clean_text"]

                            if action == "rev":
                                if current_status == "reviewed":
                                    new_status = "none"
                                    REMINDERS.pop(fix_id, None)
                                    if msg_meta.get("fs_id"):
                                        toggle_flashscore_favorite(msg_meta["fs_id"], add=False)
                                else:
                                    new_status = "reviewed"
                                    if not msg_meta.get("fs_id"):
                                        msg_meta["fs_id"] = find_flashscore_event_id(msg_meta["raw_home"], msg_meta["raw_away"])
                                    
                                    fs_id = msg_meta.get("fs_id")
                                    fs_success = False
                                    if fs_id:
                                        fs_success = toggle_flashscore_favorite(fs_id, add=True)
                                    
                                    if fs_success:
                                        send_telegram(chat_id, f"⭐️ <b>Flashscore-ზე დაემატა:</b> {msg_meta['teams']}", reply_markup=DEFAULT_KEYBOARD)
                                    else:
                                        search_q = requests.utils.quote(f"{msg_meta['raw_home']} {msg_meta['raw_away']}")
                                        fs_search_url = f"https://www.flashscore.com/search/?q={search_q}"
                                        send_telegram(chat_id, f"ℹ️ <b>Flashscore ბმული:</b> <a href='{fs_search_url}'>{msg_meta['teams']}</a>", reply_markup=DEFAULT_KEYBOARD)

                                    if msg_meta.get("match_date"):
                                        dt_clean = msg_meta["match_date"][:19]
                                        kick_dt = datetime.strptime(dt_clean, "%Y-%m-%dT%H:%M:%S")
                                        REMINDERS[fix_id] = {
                                            "kickoff_dt": kick_dt,
                                            "teams": msg_meta["teams"],
                                            "league": msg_meta["league"],
                                            "chat_id": chat_id,
                                            "sent": False
                                        }
                                
                                msg_meta["status"] = new_status
                                new_kb = make_keyboard(fix_id, new_status, msg_meta.get("fs_id"))
                                edit_message_text_and_markup(chat_id, msg_id, clean_text, new_kb)

                            elif action == "ign":
                                if current_status == "ignored":
                                    new_status = "none"
                                    updated_text = clean_text
                                else:
                                    new_status = "ignored"
                                    REMINDERS.pop(fix_id, None)
                                    if msg_meta.get("fs_id"):
                                        toggle_flashscore_favorite(msg_meta["fs_id"], add=False)
                                    lines = clean_text.split("\n")
                                    updated_text = "\n".join([f"<s>{l}</s>" if l.strip() else "" for l in lines])

                                msg_meta["status"] = new_status
                                new_kb = make_keyboard(fix_id, new_status, msg_meta.get("fs_id"))
                                edit_message_text_and_markup(chat_id, msg_id, updated_text, new_kb)
                    continue

                msg = upd.get("message")
                if not msg:
                    continue
                
                chat_id = msg["chat"]["id"]
                if chat_id != ALLOWED_CHAT_ID:
                    continue

                text = msg.get("text", "").strip()
                if text.lower() in ["სდექ", "stop", "🛑 სდექ"]:
                    IS_CANCELLED = True
                    send_telegram(chat_id, "🛑 პროცესი შეჩერებულია.", reply_markup=DEFAULT_KEYBOARD)
                    continue

                target_date, min_time, date_label = parse_user_request(text)
                send_telegram(chat_id, f"⏳ იფილტრება სათასო მატჩები ({date_label}), გთხოვთ დაელოდოთ...", reply_markup=DEFAULT_KEYBOARD)
                send_cup_matches_for_date(chat_id, target_date, min_time)

        except Exception:
            pass
        time.sleep(1)

if __name__ == "__main__":
    run_bot()
