import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sentinel.core.tool import ToolResult, ToolSpec
from sentinel.core.quality_gate import QualityGate, QualityResult
from sentinel.policies.output_policies import SENSITIVE_PATTERNS, MAX_OUTPUT_SIZE_BYTES, MAX_OUTPUT_LINES


class TestQualityGatePassThrough:
    def test_accepts_clean_string(self):
        qg = QualityGate()
        tr = ToolResult(success=True, data="hello world", tool_id="test")
        result = qg.scan(tr)
        assert result.passed
        assert not result.redacted

    def test_accepts_none_data(self):
        qg = QualityGate()
        tr = ToolResult(success=True, tool_id="test")
        result = qg.scan(tr)
        assert result.passed

    def test_accepts_empty_string(self):
        qg = QualityGate()
        tr = ToolResult(success=True, data="", tool_id="test")
        result = qg.scan(tr)
        assert result.passed


class TestQualityGateSensitivePatterns:
    def test_redacts_openai_api_key(self):
        qg = QualityGate()
        tr = ToolResult(success=True, data="the key is sk-abc123def456ghi789jkl012mno345", tool_id="test")
        result = qg.scan(tr)
        assert result.passed
        assert result.redacted
        assert "<REDACTED>" in result.redacted_data

    def test_redacts_private_key_block(self):
        qg = QualityGate()
        tr = ToolResult(
            success=True, data="-----BEGIN PRIVATE KEY-----\nABC123\n-----END PRIVATE KEY-----", tool_id="test"
        )
        result = qg.scan(tr)
        assert result.passed
        assert result.redacted
        assert "<REDACTED>" in result.redacted_data

    def test_redacts_github_token(self):
        qg = QualityGate()
        tr = ToolResult(success=True, data="token: ghp_abcdefghijklmnopqrstuvwxyz0123456789abcd", tool_id="test")
        result = qg.scan(tr)
        assert result.passed
        assert result.redacted
        assert "<REDACTED>" in result.redacted_data

    def test_redacts_aws_key(self):
        qg = QualityGate()
        tr = ToolResult(success=True, data="AWS key: AKIAIOSFODNN7EXAMPLE", tool_id="test")
        result = qg.scan(tr)
        assert result.passed
        assert result.redacted
        assert "<REDACTED>" in result.redacted_data

    def test_redacts_jwt(self):
        qg = QualityGate()
        tr = ToolResult(
            success=True,
            data="eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8",
            tool_id="test",
        )
        result = qg.scan(tr)
        assert result.passed
        assert result.redacted
        assert "<REDACTED>" in result.redacted_data

    def test_passes_plain_text(self):
        qg = QualityGate()
        tr = ToolResult(success=True, data="The quick brown fox jumps over the lazy dog", tool_id="test")
        result = qg.scan(tr)
        assert result.passed
        assert not result.redacted


class TestQualityGateSizeLimits:
    def test_blocks_oversized_output(self):
        qg = QualityGate()
        big_data = "x" * (MAX_OUTPUT_SIZE_BYTES + 1)
        tr = ToolResult(success=True, data=big_data, tool_id="test")
        result = qg.scan(tr)
        assert not result.passed
        assert any("size" in i.lower() for i in result.issues)

    def test_blocks_excessive_lines(self):
        qg = QualityGate()
        many_lines = "\n".join(f"line {i}" for i in range(MAX_OUTPUT_LINES + 2))
        tr = ToolResult(success=True, data=many_lines, tool_id="test")
        result = qg.scan(tr)
        assert not result.passed
        assert any("line" in i.lower() for i in result.issues)


class TestQualityGateDictData:
    def test_redacts_sensitive_key_in_dict_stdout(self):
        qg = QualityGate()
        tr = ToolResult(success=True, data={"stdout": "API key is sk-abc123def456ghi789jkl012mno345"}, tool_id="test")
        result = qg.scan(tr)
        assert result.passed
        assert result.redacted
        assert "<REDACTED>" in result.redacted_data.get("stdout", "")

    def test_handles_failed_result(self):
        qg = QualityGate()
        tr = ToolResult(success=False, error="permission denied", tool_id="test")
        result = qg.scan(tr)
        assert result.passed

    def test_handles_bytes_data(self):
        qg = QualityGate()
        tr = ToolResult(success=True, data=b"secret: sk-abc123xyz", tool_id="test")
        result = qg.scan(tr)
        assert result.redacted

    def test_handles_list_data(self):
        qg = QualityGate()
        tr = ToolResult(
            success=True, data=["line one", "key: ghp_abcdefghijklmnopqrstuvwxyz0123456789abcd"], tool_id="test"
        )
        result = qg.scan(tr)
        assert result.redacted
