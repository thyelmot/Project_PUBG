import http.cookiejar
from html.parser import HTMLParser
import os
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.utils.hashing import hash_file
from src.utils.logging import get_logger

logger = get_logger("pubg_download")


class _DownloadForm(HTMLParser):
    """Read the public large-file confirmation form, never an account login form."""

    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}
        self.in_download_form = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            action = attrs.get("action", "")
            parsed = urllib.parse.urlparse(action)
            self.in_download_form = (
                parsed.scheme == "https"
                and parsed.hostname in {"drive.google.com", "drive.usercontent.google.com"}
                and parsed.path in {"/download", "/uc"}
            )
            if self.in_download_form:
                self.action = action
        elif tag == "input" and self.in_download_form and attrs.get("type") == "hidden" and attrs.get("name"):
            self.fields[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_download_form = False


def _resolve_google_drive_stream(url: str) -> Any:
    """Resolve Google Drive confirmation redirects and virus scan warnings to get direct stream."""
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    opener.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")]

    # Extract ID if present
    match = re.search(r"(?:file/d/|id=)([a-zA-Z0-9_-]+)", url)
    if match and urllib.parse.urlparse(url).hostname != "drive.usercontent.google.com":
        file_id = match.group(1)
        req_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    else:
        req_url = url

    response = opener.open(req_url, timeout=60)
    content_type = response.headers.get("Content-Type", "")

    # If virus scan warning page (HTML), extract form action and hidden tokens
    if "text/html" in content_type:
        with response:
            html = response.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
        form = _DownloadForm()
        form.feed(html)
        if form.action and form.fields:
            separator = "&" if "?" in form.action else "?"
            confirm_url = form.action + separator + urllib.parse.urlencode(form.fields)
            logger.info("Following public Google Drive download confirmation (no account access).")
            response = opener.open(confirm_url, timeout=60)
        else:
            raise ValueError(
                f"Google Drive returned HTML but no confirmation form was found. "
                "The owner must enable Anyone with the link and allow downloads, or provide another public URL. "
                "This project does not request access to a personal Drive. Quotas may also block downloads."
            )

    return response


def download_file_with_checksum(
    url: str,
    target_path: Path,
    expected_checksum: Optional[str] = None,
    chunk_size: int = 1048576,  # 1MB
) -> Path:
    """Safely download a file via streaming to a temporary .part file and verify integrity."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = target_path.with_suffix(f"{target_path.suffix}.part")

    logger.info(f"Starting download: {url} -> {target_path.name}")

    try:
        if urllib.parse.urlparse(url).hostname in {"drive.google.com", "drive.usercontent.google.com"}:
            response = _resolve_google_drive_stream(url)
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "PUBG-Research-Agent/1.0"})
            response = urllib.request.urlopen(req, timeout=60)

        with response, open(part_path, "wb") as out_file:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type:
                raise ValueError(
                    f"Download URL returned HTML content ({content_type}) instead of data binary/csv. "
                    "This usually indicates an expired link or authentication page."
                )

            while chunk := response.read(chunk_size):
                out_file.write(chunk)

        # Checksum validation if provided
        if expected_checksum:
            actual_checksum = hash_file(part_path, algorithm="sha256")
            if actual_checksum.lower() != expected_checksum.lower():
                raise ValueError(
                    f"Checksum mismatch for {target_path.name}! "
                    f"Expected: {expected_checksum}, Actual: {actual_checksum}"
                )

        part_path.replace(target_path)
        logger.info(f"Download complete and verified: {target_path.name}")
        return target_path

    except Exception as e:
        if part_path.exists():
            part_path.unlink()
        logger.error(f"Download failed for {url}: {e}")
        raise e


def resolve_archive(
    archive_url: str,
    target_dir: Path,
    expected_checksum: Optional[str] = None,
    archive_filename: str = "Data_PUBG.zip",
) -> Path:
    """Locate or download the ZIP without expanding it on disk."""
    target_dir.mkdir(parents=True, exist_ok=True)

    # Check if archive exists locally in parent or target
    candidate_archives = [
        target_dir / archive_filename,
        target_dir.parent / archive_filename,
        Path(archive_filename),
        Path("..") / archive_filename,
    ]
    local_archive = None
    for cand in candidate_archives:
        if cand.is_file():
            local_archive = cand.resolve()
            break

    if local_archive is None:
        download_target = target_dir.parent / archive_filename
        logger.info(f"Local archive not found. Downloading from: {archive_url}")
        local_archive = download_file_with_checksum(archive_url, download_target, expected_checksum)

    if expected_checksum and hash_file(local_archive).lower() != expected_checksum.lower():
        raise ValueError(f"Checksum mismatch for local archive: {local_archive}")

    return local_archive


def download_and_extract_archive(
    archive_url: str,
    target_dir: Path,
    expected_checksum: Optional[str] = None,
    archive_filename: str = "Data_PUBG.zip",
) -> Path:
    """Legacy full extraction; notebooks use streaming ingestion instead."""
    local_archive = resolve_archive(archive_url, target_dir, expected_checksum, archive_filename)

    logger.info(f"Using archive {local_archive.name}. Extracting -> {target_dir}...")
    with zipfile.ZipFile(local_archive, "r") as zip_ref:
        root = target_dir.resolve()
        for member in zip_ref.infolist():
            destination = (root / member.filename.replace("\\", "/")).resolve()
            if not destination.is_relative_to(root) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Unsafe ZIP entry: {member.filename}")
        zip_ref.extractall(target_dir)

    logger.info(f"Extraction completed successfully into {target_dir}.")
    return target_dir


def resolve_local_sources(raw_dir: Path, patterns: List[str]) -> List[Path]:
    """Discover existing local data shards matching glob patterns."""
    matched: List[Path] = []
    for pattern in patterns:
        matched.extend(list(raw_dir.glob(pattern)))
    return sorted(list(set(matched)))
