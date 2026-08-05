"""Tests for the desktop OAuth loopback listener."""

import time
import urllib.request

import pytest

from services.oauth_loopback import OAuthLoopbackServer


class TestOAuthLoopback:
    @pytest.fixture
    def server(self):
        s = OAuthLoopbackServer()
        yield s
        s.stop()

    def test_binds_only_loopback(self, server):
        redirect = server.start()
        host = redirect.split("://")[1].split(":")[0]
        assert host == "127.0.0.1"

    def test_uses_random_port(self, server):
        s1 = OAuthLoopbackServer()
        s2 = OAuthLoopbackServer()
        try:
            r1 = s1.start()
            r2 = s2.start()
            p1 = int(r1.split(":")[-1].split("/")[0])
            p2 = int(r2.split(":")[-1].split("/")[0])
            assert p1 != p2
        finally:
            s1.stop()
            s2.stop()

    def test_accepts_exact_callback_path(self, server):
        redirect = server.start()
        path = "/oauth/callback?code=abc&state=xyz"
        url = redirect.replace("/oauth/callback", path)
        req = urllib.request.Request(url, method="GET", headers={"Host": f"127.0.0.1:{redirect.split(':')[-1].split('/')[0]}"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            assert resp.status == 200
        result = server.wait_for_callback(timeout=2)
        assert result["status"] == "received"
        assert result["code"] == "abc"
        assert result["state"] == "xyz"

    def test_rejects_post(self, server):
        redirect = server.start()
        url = redirect
        req = urllib.request.Request(url, method="POST", data=b"")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=2)
        assert exc.value.code == 405

    def test_rejects_wrong_path(self, server):
        redirect = server.start()
        url = redirect.replace("/oauth/callback", "/other")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url, timeout=2)
        assert exc.value.code == 404

    def test_rejects_duplicate_callback(self, server):
        redirect = server.start()
        base = redirect
        urllib.request.urlopen(base + "?code=1&state=s", timeout=2)
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(base + "?code=2&state=s", timeout=2)
        assert exc.value.code == 400

    def test_times_out_and_closes(self, server):
        server.start()
        result = server.wait_for_callback(timeout=0.5)
        assert result["status"] == "timeout"
