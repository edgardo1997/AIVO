from __future__ import annotations

import logging
import http.client
import re
import ssl
import threading
import time
import ipaddress
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from .content_security import scan_untrusted_content, wrap_untrusted_content

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15
MAX_CONTENT_SIZE = 512 * 1024


@dataclass
class WebResult:
    url: str
    title: str = ""
    text: str = ""
    html: str = ""
    links: List[Dict[str, str]] = field(default_factory=list)
    status_code: int = 0
    headers: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0
    security_indicators: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "text_preview": self.text[:2000] if self.text else "",
            "text_length": len(self.text),
            "links_count": len(self.links),
            "status_code": self.status_code,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "security_indicators": list(self.security_indicators),
        }

    @property
    def success(self) -> bool:
        return self.error is None and self.status_code == 200


class WebBrowsingService:
    def __init__(self):
        self._lock = threading.RLock()
        self._stats: Dict[str, Any] = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "last_request": None,
            "last_error": None,
        }

    def navigate(self, url: str, *, timeout: int = DEFAULT_TIMEOUT, extract_links: bool = True) -> WebResult:
        start = time.perf_counter()
        parsed = urlparse(url)
        if not parsed.scheme:
            url = "https://" + url
            parsed = urlparse(url)
        if not parsed.netloc:
            return self._record_result(WebResult(url=url, error=f"Invalid URL: {url}", duration_ms=0))
        try:
            self._validate_public_url(url)
        except ValueError as exc:
            return self._record_result(WebResult(url=url, error=str(exc), duration_ms=0))

        try:
            final_url, status, headers, body = self.fetch_public_bytes(
                url, timeout=timeout, max_bytes=MAX_CONTENT_SIZE
            )
            duration = (time.perf_counter() - start) * 1000
            result = WebResult(url=final_url, status_code=status, headers=headers, duration_ms=duration)
            if status != 200:
                result.error = f"HTTP {status}"
                return self._record_result(result)
            content = body.decode("utf-8", errors="replace")
            result.html = content
            self._extract_content(result, content, extract_links)
            return self._record_result(result)
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return self._record_result(WebResult(url=url, error=str(e), duration_ms=duration))

    def extract_text(self, url: str, *, timeout: int = DEFAULT_TIMEOUT) -> str:
        result = self.navigate(url, timeout=timeout, extract_links=False)
        if result.error:
            return f"Error fetching {url}: {result.error}"
        return result.text

    def extract_links(self, url: str, *, timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
        result = self.navigate(url, timeout=timeout, extract_links=True)
        if result.error:
            return []
        return result.links

    def search_web(self, query: str, *, num_results: int = 5) -> List[Dict[str, str]]:
        search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        result = self.navigate(search_url, timeout=DEFAULT_TIMEOUT)
        if result.error:
            logger.warning("Web search failed: %s", result.error)
            return []
        results = []
        seen_urls = set()
        for link in result.links:
            href = link.get("href", "")
            text = link.get("text", "")
            if not href or not text:
                continue
            if href.startswith("//"):
                href = "https:" + href
            if not href.startswith(("http://", "https://")):
                continue
            domain = urlparse(href).netloc
            if any(skip in domain for skip in ("duckduckgo", "duck.co")):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)
            results.append({"url": href, "title": text.strip()})
            if len(results) >= num_results:
                break
        return results

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._stats)

    @staticmethod
    def _validate_public_url(url: str) -> None:
        WebBrowsingService._resolve_public_url(url)

    @staticmethod
    def _resolve_public_url(url: str):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Only absolute HTTP/HTTPS URLs are allowed")
        if parsed.username or parsed.password:
            raise ValueError("Credentials in URLs are not allowed")
        host = parsed.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            raise ValueError("Private or local network destinations are blocked")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            addresses = {item[4][0] for item in socket.getaddrinfo(host, port)}
        except socket.gaierror as exc:
            raise ValueError(f"Host resolution failed: {host}") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ValueError("Private, loopback, link-local, and reserved destinations are blocked")
        if port not in (80, 443):
            raise ValueError("Only standard HTTP/HTTPS ports are allowed")
        return parsed, tuple(sorted(addresses))

    @classmethod
    def fetch_public_bytes(
        cls,
        url: str,
        *,
        timeout: int,
        max_bytes: int,
        require_https: bool = False,
    ) -> tuple[str, int, dict, bytes]:
        current_url = url
        for _ in range(6):
            parsed, addresses = cls._resolve_public_url(current_url)
            if require_https and parsed.scheme != "https":
                raise ValueError("This download requires HTTPS")
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            target = parsed.path or "/"
            if parsed.query:
                target += f"?{parsed.query}"
            last_error: Optional[Exception] = None
            for address in addresses:
                connection = None
                try:
                    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
                    connection = connection_type(parsed.hostname, port, timeout=timeout)
                    raw_socket = socket.create_connection((address, port), timeout=timeout)
                    if parsed.scheme == "https":
                        connection.sock = ssl.create_default_context().wrap_socket(
                            raw_socket,
                            server_hostname=parsed.hostname,
                        )
                    else:
                        connection.sock = raw_socket
                    connection.request(
                        "GET",
                        target,
                        headers={"Host": parsed.netloc, "User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
                    )
                    response = connection.getresponse()
                    headers = {key.lower(): value for key, value in response.getheaders()}
                    if response.status in (301, 302, 303, 307, 308):
                        location = headers.get("location")
                        if not location:
                            raise ValueError("Redirect response is missing a destination")
                        current_url = urljoin(current_url, location)
                        break
                    declared_size = int(headers.get("content-length", "0") or 0)
                    if declared_size > max_bytes:
                        raise ValueError("Remote response exceeds the allowed size")
                    body = response.read(max_bytes + 1)
                    if len(body) > max_bytes:
                        raise ValueError("Remote response exceeds the allowed size")
                    return current_url, response.status, headers, body
                except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                    last_error = exc
                finally:
                    if connection is not None:
                        connection.close()
            else:
                raise ValueError("Connection to the validated public destination failed") from last_error
        raise ValueError("Too many redirects")

    def _record_result(self, result: WebResult) -> WebResult:
        with self._lock:
            self._stats["total_requests"] += 1
            if result.success:
                self._stats["successful_requests"] += 1
            else:
                self._stats["failed_requests"] += 1
            self._stats["last_request"] = result.url
            if result.error:
                self._stats["last_error"] = result.error
        return result

    def _extract_content(self, result: WebResult, html: str, extract_links: bool):
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            if soup.title and soup.title.string:
                result.title = soup.title.string.strip()

            for tag in soup(
                ["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "svg", "form", "button"]
            ):
                tag.decompose()

            if extract_links:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text(strip=True)[:200]
                    if href and text:
                        result.links.append({"href": href, "text": text})

            text_parts = []
            for tag in soup.find_all(
                ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "blockquote", "pre", "code", "div", "span"]
            ):
                t = tag.get_text(strip=True)
                if t and len(t) > 1:
                    text_parts.append(t)

            result.text = "\n".join(text_parts)
            result.text = re.sub(r"\n{3,}", "\n\n", result.text).strip()
            security = scan_untrusted_content(result.text)
            result.security_indicators = list(security.indicators)
            result.text = wrap_untrusted_content(result.text)
        except ImportError:
            result.text = "BeautifulSoup not available. Install beautifulsoup4 for HTML parsing."
            result.error = "missing_dependency: beautifulsoup4"
        except Exception as e:
            logger.warning("Content extraction failed: %s", e)
            result.text = f"Content extraction error: {e}"
