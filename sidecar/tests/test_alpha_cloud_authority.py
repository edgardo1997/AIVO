import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sentinel.core.router_types import ProviderSpec
from sentinel.providers.provider_manager import ProviderManager
from sentinel.security.cloud_authority import CloudAuthority, CloudAuthorizationError, CloudExecutionAuthorization


def make_cloud_spec():
    return ProviderSpec(
        id="openrouter",
        name="OpenRouter",
        task_types=[],
        requires_key=True,
        is_local=False,
        default_model="deepseek/deepseek-v4-flash:free",
    )


def make_local_spec():
    return ProviderSpec(
        id="sentinel_local",
        name="Sentinel Local",
        task_types=[],
        requires_key=False,
        is_local=True,
        default_model="Qwen3-1.7B-Q8_0.gguf",
    )


@pytest.mark.alpha_constitutional_gate
@pytest.mark.asyncio
async def test_cloud_blocked_without_authorization():
    ca = CloudAuthority()
    pm = ProviderManager(cloud_authority=ca)
    with pytest.raises(CloudAuthorizationError):
        pm._assert_cloud_authorized(make_cloud_spec(), "deepseek/deepseek-v4-flash:free")


@pytest.mark.alpha_constitutional_gate
@pytest.mark.asyncio
async def test_local_allowed_without_authorization():
    ca = CloudAuthority()
    pm = ProviderManager(cloud_authority=ca)
    # local providers do not require cloud authority
    pm._assert_cloud_authorized(make_local_spec(), "Qwen3-1.7B-Q8_0.gguf")


@pytest.mark.alpha_constitutional_gate
@pytest.mark.asyncio
async def test_standing_policy_allows_cloud():
    ca = CloudAuthority()
    policy = CloudExecutionAuthorization(
        cloud_allowed=True,
        allowed_providers=["openrouter"],
        allowed_models=["deepseek/deepseek-v4-flash:free"],
    )
    ca.add_standing_policy(policy)
    pm = ProviderManager(cloud_authority=ca)
    pm._assert_cloud_authorized(make_cloud_spec(), "deepseek/deepseek-v4-flash:free")


@pytest.mark.alpha_constitutional_gate
@pytest.mark.asyncio
async def test_local_only_blocks_cloud():
    ca = CloudAuthority()
    ca.set_local_only(True)
    pm = ProviderManager(cloud_authority=ca)
    with pytest.raises(CloudAuthorizationError):
        pm._assert_cloud_authorized(make_cloud_spec(), "deepseek/deepseek-v4-flash:free")


@pytest.mark.alpha_constitutional_gate
def test_one_time_consent_scope():
    ca = CloudAuthority()
    consent = ca.issue_one_time_consent("openrouter", "deepseek/deepseek-v4-flash:free")
    assert ca.is_authorized("openrouter", "deepseek/deepseek-v4-flash:free")
    ca.consume_one_time_consent(consent)
    assert not ca.is_authorized("openrouter", "deepseek/deepseek-v4-flash:free")
