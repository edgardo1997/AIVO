"""Canonical embedding authority tests."""

import pytest
from sentinel.core.model_schemas import EmbeddingRequest
from sentinel.providers.provider_manager import ProviderManager
from sentinel.security.cloud_authority import CloudAuthority, CloudAuthorizationError


def test_cloud_embedding_requires_authority():
    pm = ProviderManager(cloud_authority=CloudAuthority())
    req = EmbeddingRequest(texts=["hello"], local_only=False, cloud_allowed=True, provider_preference="openrouter")
    with pytest.raises(CloudAuthorizationError):
        pm.execute_embedding(req, model="openai/text-embedding-3-small")


def test_local_embedding_prefers_token():
    pm = ProviderManager()
    req = EmbeddingRequest(texts=["hello"], local_only=True)
    with pytest.raises(RuntimeError):
        pm.execute_embedding(req)
