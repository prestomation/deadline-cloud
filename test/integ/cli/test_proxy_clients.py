# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Proxy/CA bundle integration tests.

These tests run inside a network namespace where the ONLY path to the internet
is through a MITM TLS-intercepting HTTP CONNECT proxy. The proxy generates an
ephemeral CA at startup and issues per-host certificates on the fly.

This proves that every network client in the codebase:
  1. Reads HTTPS_PROXY (or it gets "Network unreachable")
  2. Reads AWS_CA_BUNDLE (or TLS verification fails against the MITM cert)

Any code that hardcodes its own CA bundle, bypasses proxy env vars, or opens
direct connections will fail here.

See test/integ/proxy_ca_bundle/ for the proxy and namespace setup.
"""

import pytest

import boto3
from botocore.config import Config

from deadline.client.api._telemetry import TelemetryClient
from deadline.client.config import config_file


@pytest.fixture()
def telemetry_client(fresh_deadline_config):
    """Create a real telemetry client that connects to the actual endpoint."""
    config = config_file.read_config()
    client = TelemetryClient(
        package_name="deadline-cloud-library",
        package_ver="0.0.0-integ-test",
        config=config,
    )
    yield client
    if client.is_initialized:
        client._exit_cleanly()


@pytest.mark.proxy
def test_sts_through_proxy() -> None:
    """Control: STS (no host_prefix) works through the MITM proxy."""
    sts = boto3.Session().client("sts")
    resp = sts.get_caller_identity()
    assert "Account" in resp


@pytest.mark.proxy
def test_deadline_list_farms() -> None:
    """boto3 Deadline client works through the MITM proxy."""
    dl = boto3.Session().client(
        "deadline", config=Config(retries={"max_attempts": 1})
    )
    resp = dl.list_farms(maxResults=1)
    assert "farms" in resp


@pytest.mark.proxy
def test_telemetry_client_initializes(telemetry_client: TelemetryClient) -> None:
    """Telemetry client resolves its endpoint through the proxy."""
    assert telemetry_client.is_initialized
    assert telemetry_client.endpoint.startswith("https://management.")


@pytest.mark.proxy
@pytest.mark.timeout(30)
def test_telemetry_event_send(telemetry_client: TelemetryClient) -> None:
    """Telemetry HTTP send completes through the MITM proxy."""
    assert telemetry_client.is_initialized, (
        "Telemetry client failed to initialize — endpoint may be unreachable "
        "through the proxy."
    )

    telemetry_client.record_event(
        event_type="com.amazon.rum.deadline.integ_test",
        event_details={"test": True},
    )

    thread = telemetry_client.processing_thread
    while not telemetry_client.event_queue.empty() and thread.is_alive():
        thread.join(timeout=0.1)

    assert thread.is_alive(), (
        "Telemetry processing thread died — the HTTP send likely failed. "
        "Check that the telemetry endpoint is reachable and proxy/CA certs "
        "are configured correctly."
    )
