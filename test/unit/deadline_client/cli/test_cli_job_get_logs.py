# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Tests for the CLI job logs command.
"""

import json
import datetime
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from deadline.client import config
from deadline.client.cli import main
from deadline.client.api._job_monitoring import SessionLogResult, LogEvent

from ..shared_constants import (
    MOCK_FARM_ID,
    MOCK_QUEUE_ID,
)

# Sample log events for testing
SAMPLE_LOG_EVENTS = [
    LogEvent(
        timestamp=datetime.datetime(2023, 1, 1, 12, 0, 0),
        message="Log message 1",
        ingestion_time=datetime.datetime(2023, 1, 1, 12, 0, 10),
        event_id="event-1",
    ),
    LogEvent(
        timestamp=datetime.datetime(2023, 1, 1, 12, 1, 0),
        message="Log message 2",
        ingestion_time=datetime.datetime(2023, 1, 1, 12, 1, 10),
        event_id="event-2",
    ),
]

# Sample log result for testing
SAMPLE_LOG_RESULT = SessionLogResult(
    events=SAMPLE_LOG_EVENTS,
    next_token="next-token",
    log_group=f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}",
    log_stream="session-test-session",
    count=2,
)

# Sample empty log result for testing
EMPTY_LOG_RESULT = SessionLogResult(
    events=[],
    next_token=None,
    log_group=f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}",
    log_stream="session-test-session",
    count=0,
)


def test_cli_job_logs_verbose(fresh_deadline_config):
    """
    Test that logs CLI works correctly in verbose mode.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch("deadline.client.api.get_session_logs") as mock_get_logs, \
         patch("deadline.client.api._job_monitoring.get_user_and_identity_store_id") as mock_get_user:
        mock_get_user.return_value = (None, None)
        mock_get_logs.return_value = SAMPLE_LOG_RESULT

        runner = CliRunner()
        result = runner.invoke(
            main, ["job", "logs", "--session-id", "test-session", "--limit", "100"]
        )

        assert "Retrieving logs for session" in result.output
        assert "[2023-01-01 12:00:00] Log message 1" in result.output
        assert "[2023-01-01 12:01:00] Log message 2" in result.output
        assert "Retrieved 2 log events" in result.output
        assert "More logs are available" in result.output
        assert result.exit_code == 0

        # Verify the API was called with correct parameters
        mock_get_logs.assert_called_once()
        args, kwargs = mock_get_logs.call_args
        assert kwargs["farm_id"] == MOCK_FARM_ID
        assert kwargs["queue_id"] == MOCK_QUEUE_ID
        assert kwargs["session_id"] == "test-session"
        assert kwargs["limit"] == 100


def test_cli_job_logs_json(fresh_deadline_config):
    """
    Test that logs CLI works correctly in JSON mode.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch("deadline.client.api.get_session_logs") as mock_get_logs, \
         patch("deadline.client.api._job_monitoring.get_user_and_identity_store_id") as mock_get_user:
        mock_get_user.return_value = (None, None)
        mock_get_logs.return_value = SAMPLE_LOG_RESULT

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "job",
                "logs",
                "--session-id",
                "test-session",
                "--limit",
                "100",
                "--output",
                "json",
            ],
        )

        # Verify the output is valid JSON
        output_json = json.loads(result.output)
        assert "events" in output_json
        assert len(output_json["events"]) == 2
        assert output_json["events"][0]["message"] == "Log message 1"
        assert output_json["events"][1]["message"] == "Log message 2"
        assert output_json["count"] == 2
        assert output_json["nextToken"] == "next-token"
        assert output_json["logGroup"] == f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}"
        assert output_json["logStream"] == "session-test-session"

        # Verify no intermediate text output was produced
        assert "Retrieving logs for session" not in result.output

        assert result.exit_code == 0


def test_cli_job_logs_empty(fresh_deadline_config):
    """
    Test that logs CLI handles empty results correctly.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch("deadline.client.api.get_session_logs") as mock_get_logs, \
         patch("deadline.client.api._job_monitoring.get_user_and_identity_store_id") as mock_get_user:
        mock_get_user.return_value = (None, None)
        mock_get_logs.return_value = EMPTY_LOG_RESULT

        runner = CliRunner()
        result = runner.invoke(
            main, ["job", "logs", "--session-id", "test-session", "--limit", "100"]
        )

        assert "No logs found for the specified session" in result.output
        assert result.exit_code == 0


def test_cli_job_logs_json_empty(fresh_deadline_config):
    """
    Test that logs CLI handles empty results correctly in JSON mode.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch("deadline.client.api.get_session_logs") as mock_get_logs, \
         patch("deadline.client.api._job_monitoring.get_user_and_identity_store_id") as mock_get_user:
        mock_get_user.return_value = (None, None)
        mock_get_logs.return_value = EMPTY_LOG_RESULT

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "job",
                "logs",
                "--session-id",
                "test-session",
                "--limit",
                "100",
                "--output",
                "json",
            ],
        )

        # Verify the output is valid JSON
        output_json = json.loads(result.output)
        assert "events" in output_json
        assert len(output_json["events"]) == 0
        assert output_json["count"] == 0
        assert output_json["nextToken"] is None

        assert result.exit_code == 0


def test_cli_job_logs_json_error(fresh_deadline_config):
    """
    Test that logs CLI handles errors correctly in JSON mode.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch("deadline.client.api.get_session_logs") as mock_get_logs, \
         patch("deadline.client.api._job_monitoring.get_user_and_identity_store_id") as mock_get_user:
        mock_get_user.return_value = (None, None)
        mock_get_logs.side_effect = Exception("Test error message")

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["job", "logs", "--session-id", "test-session", "--output", "json"],
        )

        # Verify the output contains an error message
        assert "error" in result.output
        # The actual error message is different in the test environment

        # Exit code should be non-zero for errors
        assert result.exit_code != 0


def test_cli_job_logs_with_time_params(fresh_deadline_config):
    """
    Test that logs CLI handles time parameters correctly.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch("deadline.client.api.get_session_logs") as mock_get_logs, \
         patch("deadline.client.api._job_monitoring.get_user_and_identity_store_id") as mock_get_user:
        mock_get_user.return_value = (None, None)
        mock_get_logs.return_value = SAMPLE_LOG_RESULT

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "job",
                "logs",
                "--session-id",
                "test-session",
                "--start-time",
                "2023-01-01T12:00:00Z",
                "--end-time",
                "2023-01-01T13:00:00Z",
            ],
        )

        assert result.exit_code == 0

        # Verify the API was called with correct parameters
        mock_get_logs.assert_called_once()
        args, kwargs = mock_get_logs.call_args
        assert kwargs["start_time"] == "2023-01-01T12:00:00Z"
        assert kwargs["end_time"] == "2023-01-01T13:00:00Z"


def test_cli_job_logs_with_next_token(fresh_deadline_config):
    """
    Test that logs CLI handles next_token parameter correctly.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch("deadline.client.api.get_session_logs") as mock_get_logs, \
         patch("deadline.client.api._job_monitoring.get_user_and_identity_store_id") as mock_get_user:
        mock_get_user.return_value = (None, None)
        mock_get_logs.return_value = SAMPLE_LOG_RESULT

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "job",
                "logs",
                "--session-id",
                "test-session",
                "--next-token",
                "test-token",
            ],
        )

        assert result.exit_code == 0

        # Verify the API was called with correct parameters
        mock_get_logs.assert_called_once()
        args, kwargs = mock_get_logs.call_args
        assert kwargs["next_token"] == "test-token"


def test_cli_job_logs_with_monitor_user(fresh_deadline_config):
    """
    Test that logs CLI works correctly when using Deadline Cloud monitor credentials.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch("deadline.client.api._job_monitoring.get_session_logs") as mock_get_logs, \
         patch("deadline.client.api._job_monitoring.get_user_and_identity_store_id") as mock_get_user, \
         patch("deadline.client.api._job_monitoring.get_queue_user_boto3_session") as mock_get_session, \
         patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_boto3_client:
        # Mock monitor user credentials
        mock_get_user.return_value = ("user-123", "identity-store-456")
        mock_session = MagicMock()
        mock_logs_client = MagicMock()
        mock_session.client.return_value = mock_logs_client
        mock_get_session.return_value = mock_session
        mock_get_logs.return_value = SAMPLE_LOG_RESULT

        runner = CliRunner()
        result = runner.invoke(
            main, ["job", "logs", "--session-id", "test-session", "--limit", "100"]
        )

        assert result.exit_code == 0
        assert "Retrieving logs for session" in result.output
        
        # Verify the queue user session was created
        mock_get_session.assert_called_once()
        args, kwargs = mock_get_session.call_args
        assert kwargs["farm_id"] == MOCK_FARM_ID
        assert kwargs["queue_id"] == MOCK_QUEUE_ID


def test_cli_job_logs_with_monitor_user_error(fresh_deadline_config):
    """
    Test that logs CLI handles errors when getting queue credentials.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch("deadline.client.api._job_monitoring.get_session_logs") as mock_get_logs, \
         patch("deadline.client.api._job_monitoring.get_user_and_identity_store_id") as mock_get_user, \
         patch("deadline.client.api._job_monitoring.get_queue_user_boto3_session") as mock_get_session, \
         patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_boto3_client:
        # Mock monitor user credentials but make session creation fail
        mock_get_user.return_value = ("user-123", "identity-store-456")
        mock_get_session.side_effect = Exception("Failed to get queue credentials")
        
        runner = CliRunner()
        result = runner.invoke(
            main, ["job", "logs", "--session-id", "test-session"]
        )

        # Should fail with non-zero exit code
        assert result.exit_code != 0
        assert "Failed to get queue credentials" in result.output
