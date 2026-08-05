"""Tests for the desktop OAuth loopback listener."""

import urllib.error
import urllib.request

import pytest

from services.oauth_loopback import OAuthLoopbackServer


class TestOAuthLoopback:
    def test_binds_only_loopback(self):
        server = OAuthLoopbackServer()
        try:
            redirect = server.start()
            assert redirect.startswith("http://127.0.0.1:")
        finally:
            server.stop()

    def test_uses_random_port(self):
        ports = set()
        servers = []
        try:
            for _ in range(3):
                s = OAuthLoopbackServer()
                servers.append(s)
                redirect = s.start()
                ports.add(int(redirect.split(":")[-1].split("/")[0]))
            assert len(ports) == 3
        finally:
            for s in servers:
                s.stop()

    def test_accepts_exact_callback_path(self):
        server = OAuthLoopbackServer()
        try:
            redirect = server.start()
            port = redirect.split(":")[-1].split("/")[0]
            path = f"/oauth/callback?code=abc&state=xyz"
            url = f"http://127.0.0.1:{port}{path}"
            req = urllib.request.Request(url, method="GET", headers={"Host": f"127.0.0.1:{port}"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                assert resp.status == 200
        finally:
            server.stop()

    def test_rejects_post(self):
        server = OAuthLoopbackServer()
        try:
            redirect = server.start()
            url = redirect
            req = urllib.request.Request(url, method="POST", data=b"")
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(req, timeout=2)
            assert exc.value.code == 405
        finally:
            server.stop()

    def test_rejects_wrong_path(self):
        server = OAuthLoopbackServer()
        try:
            redirect = server.start()
            url = redirect.replace("/oauth/callback", "/other")
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(url, timeout=2)
            assert exc.value.code == 404
        finally:
            server.stop()

    def test_rejects_duplicate_callback(self):
        server = OAuthLoopbackServer()
        try:
            redirect = server.start()
            port = redirect.split(":")[-1].split("/")[0]
            urllib.request.urlopen(f"http://127.0.0.1:{port}/oauth/callback?code=1&state=s", timeout=2)
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/oauth/callback?code=2&state=s", timeout=2)
            assert exc.value.code == 400
        finally:
            server.stop()

    def test_times_out_and_closes(self):
        server = OAuthLoopbackServer()
        try:
            server.start(timeout=0.3)
            result = server.wait_for_callback(timeout=0.5)
            assert result["status"] == "timeout"
        finally:
            server.stop()
