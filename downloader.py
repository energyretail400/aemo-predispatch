"""
Downloads the latest AEMO ZIP files from NEMWEB.
"""

import re
import zipfile
import requests
from bs4 import BeautifulSoup
from pathlib import Path

INPUT_FOLDER = Path(__file__).parent / "data"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _download_zip(url: str, dest: Path) -> None:
    """Download url → dest, then verify it is a valid ZIP. Deletes and raises on failure."""
    with requests.get(url, stream=True, timeout=120, headers=HEADERS) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
    if not zipfile.is_zipfile(dest):
        dest.unlink(missing_ok=True)
        raise ValueError(f"Downloaded file is not a valid ZIP: {url}")


def _scrape(url: str, pattern: re.Pattern) -> list[dict]:
    """Return [{name, url, date}] from a NEMWEB directory listing, newest first."""
    resp = requests.get(url, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    files = []
    for a in soup.find_all("a", href=True):
        name = a["href"].split("/")[-1]
        m = pattern.search(name)
        if m:
            href = a["href"]
            full_url = href if href.startswith("http") else url + name
            files.append({"name": name, "url": full_url, "date": m.group(1)})
    files.sort(key=lambda x: x["date"], reverse=True)
    return files


# ── Medium Term PASA ─────────────────────────────────────────────────────────

MTPASA_URL     = "https://www.nemweb.com.au/REPORTS/CURRENT/Medium_Term_PASA_Reports/"
MTPASA_PATTERN = re.compile(r"PUBLIC_MTPASA_(\d{12})_\d+\.zip", re.IGNORECASE)


def download_latest_mtpasa() -> tuple[Path | None, str]:
    folder = INPUT_FOLDER / "MTPASA"
    folder.mkdir(parents=True, exist_ok=True)
    files = _scrape(MTPASA_URL, MTPASA_PATTERN)
    if not files:
        return None, "No MTPASA files found on NEMWEB."
    newest = files[0]
    dest   = folder / newest["name"]
    if dest.exists() and zipfile.is_zipfile(dest):
        return dest, f"MTPASA data is up to date ({newest['name']})"
    try:
        _download_zip(newest["url"], dest)
    except Exception as e:
        return None, f"MTPASA download failed: {e}"
    return dest, f"Downloaded: {newest['name']}"


def get_latest_mtpasa_local() -> Path | None:
    folder = INPUT_FOLDER / "MTPASA"
    folder.mkdir(parents=True, exist_ok=True)
    valid = [p for p in folder.glob("PUBLIC_MTPASA_*.zip") if zipfile.is_zipfile(p)]
    return max(valid, key=lambda p: MTPASA_PATTERN.search(p.name).group(1), default=None) if valid else None


def count_mtpasa_local_files() -> int:
    folder = INPUT_FOLDER / "MTPASA"
    folder.mkdir(parents=True, exist_ok=True)
    return sum(1 for p in folder.glob("PUBLIC_MTPASA_*.zip") if zipfile.is_zipfile(p))


# ── Short Term PASA ───────────────────────────────────────────────────────────

STPASA_URL = "https://www.nemweb.com.au/REPORTS/CURRENT/Short_Term_PASA_Reports/"
STPASA_PATTERN = re.compile(r"PUBLIC_STPASA_(\d{12})_\d+\.zip", re.IGNORECASE)


def download_latest_stpasa() -> tuple[Path | None, str]:
    folder = INPUT_FOLDER / "STPASA"
    folder.mkdir(parents=True, exist_ok=True)
    files = _scrape(STPASA_URL, STPASA_PATTERN)
    if not files:
        return None, "No STPASA files found on NEMWEB."
    newest = files[0]
    dest = folder / newest["name"]
    if dest.exists() and zipfile.is_zipfile(dest):
        return dest, f"STPASA data is up to date ({newest['name']})"
    try:
        _download_zip(newest["url"], dest)
    except Exception as e:
        return None, f"STPASA download failed: {e}"
    return dest, f"Downloaded: {newest['name']}"


def get_latest_stpasa_local() -> Path | None:
    folder = INPUT_FOLDER / "STPASA"
    folder.mkdir(parents=True, exist_ok=True)
    valid = [p for p in folder.glob("PUBLIC_STPASA_*.zip") if zipfile.is_zipfile(p)]
    return max(valid, key=lambda p: STPASA_PATTERN.search(p.name).group(1), default=None) if valid else None


# ── P5 Predispatch (P5MIN) ────────────────────────────────────────────────────

P5MIN_URL = "https://www.nemweb.com.au/REPORTS/CURRENT/P5_Reports/"
P5MIN_PATTERN = re.compile(r"PUBLIC_P5MIN_(\d{12})_\d+\.zip", re.IGNORECASE)


def download_latest_p5min() -> tuple[Path | None, str]:
    folder = INPUT_FOLDER / "P5MIN"
    folder.mkdir(parents=True, exist_ok=True)
    files = _scrape(P5MIN_URL, P5MIN_PATTERN)
    if not files:
        return None, "No P5MIN files found on NEMWEB."
    newest = files[0]
    dest = folder / newest["name"]
    if dest.exists() and zipfile.is_zipfile(dest):
        return dest, f"P5MIN data is up to date ({newest['name']})"
    try:
        _download_zip(newest["url"], dest)
    except Exception as e:
        return None, f"P5MIN download failed: {e}"
    return dest, f"Downloaded: {newest['name']}"


def get_latest_p5min_local() -> Path | None:
    folder = INPUT_FOLDER / "P5MIN"
    folder.mkdir(parents=True, exist_ok=True)
    valid = [p for p in folder.glob("PUBLIC_P5MIN_*.zip") if zipfile.is_zipfile(p)]
    return max(valid, key=lambda p: P5MIN_PATTERN.search(p.name).group(1), default=None) if valid else None


# ── 30-min Predispatch ────────────────────────────────────────────────────────

PREDISPATCH_URL = "https://www.nemweb.com.au/REPORTS/CURRENT/Predispatch_Reports/"
PREDISPATCH_PATTERN = re.compile(r"PUBLIC_PREDISPATCH_(\d{12})_\d+_LEGACY\.zip", re.IGNORECASE)


def download_latest_predispatch() -> tuple[Path | None, str]:
    folder = INPUT_FOLDER / "PREDISPATCH"
    folder.mkdir(parents=True, exist_ok=True)
    files = _scrape(PREDISPATCH_URL, PREDISPATCH_PATTERN)
    if not files:
        return None, "No Predispatch files found on NEMWEB."
    newest = files[0]
    dest = folder / newest["name"]
    if dest.exists() and zipfile.is_zipfile(dest):
        return dest, f"Predispatch data is up to date ({newest['name']})"
    try:
        _download_zip(newest["url"], dest)
    except Exception as e:
        return None, f"Predispatch download failed: {e}"
    return dest, f"Downloaded: {newest['name']}"


def get_latest_predispatch_local() -> Path | None:
    folder = INPUT_FOLDER / "PREDISPATCH"
    folder.mkdir(parents=True, exist_ok=True)
    valid = [p for p in folder.glob("PUBLIC_PREDISPATCH_*_LEGACY.zip") if zipfile.is_zipfile(p)]
    return max(valid, key=lambda p: PREDISPATCH_PATTERN.search(p.name).group(1), default=None) if valid else None


# ── Dispatch IS ───────────────────────────────────────────────────────────────

DISPATCHIS_URL = "https://www.nemweb.com.au/Reports/CURRENT/DispatchIS_Reports/"
DISPATCHIS_PATTERN = re.compile(r"PUBLIC_DISPATCHIS_(\d{12})_\d+\.zip", re.IGNORECASE)


def download_latest_dispatchis() -> tuple[Path | None, str]:
    folder = INPUT_FOLDER / "DISPATCHIS"
    folder.mkdir(parents=True, exist_ok=True)
    files = _scrape(DISPATCHIS_URL, DISPATCHIS_PATTERN)
    if not files:
        return None, "No DispatchIS files found on NEMWEB."
    newest = files[0]
    dest = folder / newest["name"]
    if dest.exists() and zipfile.is_zipfile(dest):
        return dest, f"DispatchIS up to date ({newest['name']})"
    try:
        _download_zip(newest["url"], dest)
    except Exception as e:
        return None, f"DispatchIS download failed: {e}"
    return dest, f"Downloaded: {newest['name']}"


def get_latest_dispatchis_local() -> Path | None:
    folder = INPUT_FOLDER / "DISPATCHIS"
    folder.mkdir(parents=True, exist_ok=True)
    valid = [p for p in folder.glob("PUBLIC_DISPATCHIS_*.zip") if zipfile.is_zipfile(p)]
    return max(valid, key=lambda p: DISPATCHIS_PATTERN.search(p.name).group(1), default=None) if valid else None


def get_all_dispatchis_yesterday_local() -> list[Path]:
    """Return all valid local DispatchIS ZIPs for yesterday (AEST), sorted oldest first."""
    from datetime import datetime, timezone, timedelta
    aest = timezone(timedelta(hours=10))
    aest_yesterday = (datetime.now(tz=aest) - timedelta(days=1)).strftime("%Y%m%d")
    folder = INPUT_FOLDER / "DISPATCHIS"
    folder.mkdir(parents=True, exist_ok=True)
    files = [
        p for p in folder.glob("PUBLIC_DISPATCHIS_*.zip")
        if (m := DISPATCHIS_PATTERN.search(p.name)) and m.group(1).startswith(aest_yesterday)
        and zipfile.is_zipfile(p)
    ]
    return sorted(files, key=lambda p: DISPATCHIS_PATTERN.search(p.name).group(1))


def get_all_dispatchis_today_local() -> list[Path]:
    """Return all valid local DispatchIS ZIPs for today (AEST), sorted oldest first."""
    from datetime import datetime, timezone, timedelta
    aest_today = datetime.now(tz=timezone(timedelta(hours=10))).strftime("%Y%m%d")
    folder = INPUT_FOLDER / "DISPATCHIS"
    folder.mkdir(parents=True, exist_ok=True)
    files = [
        p for p in folder.glob("PUBLIC_DISPATCHIS_*.zip")
        if (m := DISPATCHIS_PATTERN.search(p.name)) and m.group(1).startswith(aest_today)
        and zipfile.is_zipfile(p)
    ]
    return sorted(files, key=lambda p: DISPATCHIS_PATTERN.search(p.name).group(1))


def download_all_dispatchis_today() -> int:
    """Download all available DispatchIS files for today (AEST) not already cached. Returns new file count."""
    from datetime import datetime, timezone, timedelta
    aest_today = datetime.now(tz=timezone(timedelta(hours=10))).strftime("%Y%m%d")
    folder = INPUT_FOLDER / "DISPATCHIS"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        all_files = _scrape(DISPATCHIS_URL, DISPATCHIS_PATTERN)
    except Exception:
        return 0
    today_files = [f for f in all_files if f["date"].startswith(aest_today)]
    local = {p.name for p in folder.glob("PUBLIC_DISPATCHIS_*.zip")}
    count = 0
    for f in today_files:
        if f["name"] not in local:
            try:
                _download_zip(f["url"], folder / f["name"])
                count += 1
            except Exception:
                pass
    return count
