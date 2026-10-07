#!/usr/bin/env python3
"""
Ghost Tracker v2 - OSINT lookup tool (educational use only)

Improvements over the original:
  - Removed hardcoded junk map link
  - Fixed lat/lon truncation (int -> float)
  - Added timeouts + error handling on all network calls
  - ipwho.is: checks "success" flag before reading fields
  - Nominatim: proper User-Agent (required by OSM policy), URL-encoded query,
    bounded results, falls back gracefully on failure
  - phonenumbers: region is now selectable instead of hardcoded "ID";
    parse errors are caught instead of crashing
  - Username checker: uses "not found" page signatures instead of naive
    status-code check; de-duplicated site list; thread pool for speed
  - Fixed exit handler and menu loop
"""

import json
import os
import sys
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor

import requests

try:
    import phonenumbers
    from phonenumbers import carrier, geocoder, timezone as pntz
except ImportError:
    phonenumbers = None

# ---------- colors ----------
Wh, Gr, Ye, Re, Cy = ('\033[1;37m', '\033[1;32m', '\033[1;33m',
                      '\033[1;31m', '\033[1;36m')
USE_COLOR = sys.stdout.isatty()
if not USE_COLOR:
    Wh = Gr = Ye = Re = Cy = ''

REQUEST_TIMEOUT = 10
HEADERS = {
    "User-Agent": "GhostTracker/2.0 (educational OSINT lookup; contact: local user)"
}

clear = lambda: os.system('cls' if os.name == 'nt' else 'clear')


def pause():
    input(f'\n{Wh}[ {Gr}+ {Wh}] Press enter to continue ')


# ================= IP TRACKER =================

def ip_track():
    ip = input(f"{Wh}\n Enter IP target : {Gr}").strip()
    print(f'\n {Wh}===== {Gr}SHOW INFORMATION IP ADDRESS {Wh}=====\n')
    try:
        r = requests.get(f"http://ipwho.is/{ip}", timeout=REQUEST_TIMEOUT)
        data = r.json()
    except requests.RequestException as e:
        print(f"{Re}Network error: {e}{Wh}")
        return
    if not data.get("success", False):
        print(f"{Re}Lookup failed: {data.get('message', 'unknown error')}{Wh}")
        return

    def show(label, value):
        print(f" {Wh}{label:<17}:{Gr} {value}")

    show("IP target", ip)
    show("Type IP", data.get("type"))
    show("Country", data.get("country"))
    show("Country Code", data.get("country_code"))
    show("City", data.get("city"))
    show("Region", data.get("region"))
    lat, lon = data.get("latitude"), data.get("longitude")
    show("Latitude", lat)
    show("Longitude", lon)
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        show("Maps", f"https://www.google.com/maps/@{lat},{lon},8z")
    show("Postal", data.get("postal"))
    show("Calling Code", data.get("calling_code"))
    show("Capital", data.get("capital"))
    conn = data.get("connection") or {}
    show("ASN", conn.get("asn"))
    show("ORG", conn.get("org"))
    show("ISP", conn.get("isp"))
    tz = data.get("timezone") or {}
    show("Timezone ID", tz.get("id"))
    show("UTC offset", tz.get("utc"))
    show("Current Time", tz.get("current_time"))


# ================= SHOW OWN IP =================

def show_own_ip():
    try:
        ip = requests.get('https://api.ipify.org', timeout=REQUEST_TIMEOUT).text.strip()
        print(f"\n {Wh}===== {Gr}SHOW INFORMATION YOUR IP {Wh}=====")
        print(f"\n {Wh}[ {Gr}+ {Wh}] Your IP Address : {Gr}{ip}\n")
    except requests.RequestException as e:
        print(f"{Re}Network error: {e}{Wh}")


# ================= PHONE TRACKER =================

def phone_track():
    if phonenumbers is None:
        print(f"{Re}phonenumbers library not installed. "
              f"Run: pip install phonenumbers{Wh}")
        return

    number = input(f"\n {Wh}Enter phone number target {Gr}Ex [+6281xxxxxxxxx] "
                   f"{Wh}: {Gr}").strip()
    region = input(f" {Wh}Default region (2-letter, e.g. ID, US, NG) "
                   f"[{Gr}ID{Wh}] : {Gr}").strip().upper() or "ID"

    try:
        parsed = phonenumbers.parse(number, region)
    except phonenumbers.NumberParseException as e:
        print(f"{Re}Could not parse number: {e}{Wh}")
        return

    location = geocoder.description_for_number(parsed, "en") or "Unknown"
    region_code = phonenumbers.region_code_for_number(parsed)
    provider = carrier.name_for_number(parsed, "en") or "Unknown"
    is_valid = phonenumbers.is_valid_number(parsed)
    is_possible = phonenumbers.is_possible_number(parsed)
    intl = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    ntype = phonenumbers.number_type(parsed)
    tz_list = list(pntz.time_zones_for_number(parsed)) or ["Unknown"]

    type_names = {
        phonenumbers.PhoneNumberType.MOBILE: "Mobile",
        phonenumbers.PhoneNumberType.FIXED_LINE: "Fixed line",
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixed line or mobile",
        phonenumbers.PhoneNumberType.VOIP: "VoIP",
        phonenumbers.PhoneNumberType.TOLL_FREE: "Toll free",
        phonenumbers.PhoneNumberType.PREMIUM_RATE: "Premium rate",
        phonenumbers.PhoneNumberType.VOICEMAIL: "Voicemail",
        phonenumbers.PhoneNumberType.PAGER: "Pager",
        phonenumbers.PhoneNumberType.UAN: "UAN",
        phonenumbers.PhoneNumberType.SHARED_COST: "Shared cost",
        phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "Personal number",
    }
    type_str = type_names.get(ntype, f"Other ({ntype})")

    print(f"\n {Wh}===== {Gr}SHOW INFORMATION PHONE NUMBER {Wh}=====")
    def show(label, value):
        print(f" {Wh}{label:<22}:{Gr} {value}")
    show("Location (prefix)", location)
    show("Region code", region_code)
    show("Timezone(s)", ", ".join(tz_list))
    show("Carrier (prefix)", provider)
    show("Valid number", is_valid)
    show("Possible number", is_possible)
    show("International format", intl)
    show("E.164 format", e164)
    show("Country code", f"+{parsed.country_code}")
    show("National number", parsed.national_number)
    show("Number type", type_str)

    # --- approximate coordinates of the prefix location (city-level at best) ---
    print(f"\n {Wh}===== {Gr}APPROXIMATE LOCATION {Wh}=====")
    print(f" {Ye}Note: coordinates are for the prefix region, NOT the phone.{Wh}")
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "limit": 1},
            headers=HEADERS, timeout=REQUEST_TIMEOUT)
        hits = r.json()
        if hits:
            lat, lon = hits[0]["lat"], hits[0]["lon"]
            link = f"https://www.google.com/maps/@{lat},{lon},10z"
            show("Latitude", lat)
            show("Longitude", lon)
            show("Maps link", link)
            open_it = input(f"\n {Wh}Open in browser? [y/N] : {Gr}").strip().lower()
            if open_it == 'y':
                webbrowser.open(link)
        else:
            print(f" {Wh}No coordinates found for '{location}'.{Wh}")
    except requests.RequestException as e:
        print(f" {Re}Geocoding failed: {e}{Wh}")


# ================= USERNAME TRACKER =================

SOCIAL_SITES = [
    # url, name, list of "not found" signature strings (lowercase)
    ("https://www.facebook.com/{}", "Facebook", ["page isn't available", "content isn't available"]),
    ("https://www.twitter.com/{}", "Twitter/X", ["this account doesn't exist"]),
    ("https://www.instagram.com/{}", "Instagram", ["page not found", "sorry, this page"]),
    ("https://www.linkedin.com/in/{}", "LinkedIn", ["profile not found", "page not found"]),
    ("https://www.github.com/{}", "GitHub", ["page not found", "not found"]),
    ("https://www.pinterest.com/{}", "Pinterest", ["user not found"]),
    ("https://www.tumblr.com/{}", "Tumblr", ["there's nothing here"]),
    ("https://www.youtube.com/@{}", "YouTube", ["this page isn't available"]),
    ("https://soundcloud.com/{}", "SoundCloud", ["page not found", "we can't find that user"]),
    ("https://www.snapchat.com/add/{}", "Snapchat", ["page not found"]),
    ("https://www.tiktok.com/@{}", "TikTok", ["couldn't find this account", "page not available"]),
    ("https://www.behance.net/{}", "Behance", ["user not found", "page not found"]),
    ("https://medium.com/@{}", "Medium", ["page not found", "user not found"]),
    ("https://www.quora.com/profile/{}", "Quora", ["page not found", "user not found"]),
    ("https://www.flickr.com/people/{}", "Flickr", ["page not found"]),
    ("https://www.twitch.tv/{}", "Twitch", ["user not found", "page not found"]),
    ("https://www.dribbble.com/{}", "Dribbble", ["page not found", "user not found"]),
    ("https://t.me/{}", "Telegram", ["username not found", "if you have telegram"]),
]

def _check_site(site, username):
    url, name, signatures = site
    target = url.format(username)
    try:
        r = requests.get(target, headers=HEADERS, timeout=REQUEST_TIMEOUT,
                         allow_redirects=True)
        body = r.text.lower()
        if r.status_code == 200 and not any(sig in body for sig in signatures):
            return name, target
    except requests.RequestException:
        pass
    return name, None

def username_track():
    username = input(f"\n {Wh}Enter Username : {Gr}").strip()
    if not username:
        print(f"{Re}Empty username.{Wh}")
        return
    print(f"\n {Wh}===== {Gr}SHOW INFORMATION USERNAME {Wh}=====\n")
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda s: _check_site(s, username), SOCIAL_SITES))
    found = 0
    for name, url in results:
        if url:
            found += 1
            print(f" {Wh}[ {Gr}+ {Wh}] {name:<10} : {Gr}{url}")
        else:
            print(f" {Wh}[ {Re}- {Wh}] {name:<10} : {Ye}not found / unavailable")
    print(f"\n {Wh}Found on {Gr}{found}{Wh}/{len(results)} sites checked.")


# ================= MENU =================

OPTIONS = [
    {'num': 1, 'text': 'IP Tracker',            'func': ip_track},
    {'num': 2, 'text': 'Show Your IP',          'func': show_own_ip},
    {'num': 3, 'text': 'Phone Number Tracker',  'func': phone_track},
    {'num': 4, 'text': 'Username Tracker',      'func': username_track},
    {'num': 0, 'text': 'Exit',                  'func': sys.exit},
]

def banner():
    sys.stderr.write(f"""
       ________               __      ______                __
      / ____/ /_  ____  _____/ /_    /_  __/________ ______/ /__
     / / __/ __ \\/ __ \\/ ___/ __/_____/ / / ___/ __ `/ ___/ //_/
    / /_/ / / / / /_/ (__  ) /_/_____/ / / /  / /_/ / /__/ ,<
    \\____/_/ /_/\\____/____/\\__/     /_/ /_/   \\__,_/\\___/_/|_|

              {Wh}[ + ]  GHOST TRACKER v2  [ + ]{Wh}
""")

def main():
    while True:
        clear()
        banner()
        print()
        for opt in OPTIONS:
            print(f'{Wh}[ {opt["num"]} ] {Gr}{opt["text"]}')
        try:
            opt = int(input(f"{Wh}\n [ + ] {Gr}Select Option : {Wh}"))
        except ValueError:
            print(f'\n{Wh}[ {Re}! {Wh}]{Re} Please input a number')
            time.sleep(1.5)
            continue
        chosen = next((o for o in OPTIONS if o['num'] == opt), None)
        if chosen is None:
            print(f'\n{Wh}[ {Re}! {Wh}]{Re} Option not found')
            time.sleep(1.5)
            continue
        clear()
        try:
            chosen['func']()
        except KeyboardInterrupt:
            print(f'\n{Wh}[ {Re}! {Wh}]{Re} Cancelled')
        if chosen['num'] != 0:
            pause()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f'\n{Wh}[ {Re}! {Wh}]{Re} Exit')
        sys.exit(0)
