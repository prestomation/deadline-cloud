# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Tests for the CLI job logs command.
"""

import datetime
from unittest.mock import ANY, MagicMock, patch, call

from click.testing import CliRunner
from dateutil.tz import tzutc

from deadline.client import api
from deadline.client.cli import main
from deadline.client.config import config_file as config

# Mock constants
MOCK_FARM_ID = "farm-0123456789abcdefabcdefabcdefabcd"
MOCK_QUEUE_ID = "queue-0123456789abcdefabcdefabcdefabcd"
MOCK_JOB_ID = "job-0123456789abcdefabcdefabcdefabcd"


def test_cli_job_logs_with_session_id(fresh_deadline_config):
    """
    Test job logs command with explicit session ID.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch.object(api, "get_session_logs") as mock_get_logs:
        # Mock the get_session_logs response
        mock_get_logs.return_value = api.SessionLogResult(
            events=[
                api.LogEvent(
                    timestamp=datetime.datetime(2023, 1, 27, 7, 24, 45, tzinfo=tzutc()),
                    message="Test log message 1",
                    ingestion_time=datetime.datetime(2023, 1, 27, 7, 24, 46, tzinfo=tzutc()),
                    event_id="event-1",
                ),
                api.LogEvent(
                    timestamp=datetime.datetime(2023, 1, 27, 7, 24, 50, tzinfo=tzutc()),
                    message="Test log message 2",
                    ingestion_time=datetime.datetime(2023, 1, 27, 7, 24, 51, tzinfo=tzutc()),
                    event_id="event-2",
                ),
            ],
            count=2,
            next_token=None,
            log_group=f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}",
            log_stream="session-1",
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "job",
                "logs",
                "--session-id",
                "session-1",
            ],
        )

        # Verify the API was called correctly
        mock_get_logs.assert_called_once_with(
            farm_id=MOCK_FARM_ID,
            queue_id=MOCK_QUEUE_ID,
            session_id="session-1",
            limit=100,
            start_time=None,
            end_time=None,
            next_token=None,
            config=ANY,
        )

        # Check output
        assert "Retrieving logs for session session-1" in result.output
        assert "2023-01-27 07:24:45" in result.output
        assert "Test log message 1" in result.output
        assert "2023-01-27 07:24:50" in result.output
        assert "Test log message 2" in result.output
        assert "Retrieved 2 log events" in result.output
        assert result.exit_code == 0


def test_cli_job_logs_with_job_id_single_session(fresh_deadline_config):
    """
    Test job logs command with job ID when there's only one session.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)
    config.set_setting("defaults.job_id", MOCK_JOB_ID)

    with patch.object(api, "get_boto3_client") as boto3_client_mock, patch.object(
        api, "get_session_logs"
    ) as mock_get_logs:
        # Mock the paginator
        paginator_mock = MagicMock()
        boto3_client_mock().get_paginator.return_value = paginator_mock
        
        # Set up the paginator to return a single session
        paginator_mock.paginate.return_value = [
            {"sessions": [{"sessionId": "session-1"}]}
        ]

        # Mock the get_session_logs response
        mock_get_logs.return_value = api.SessionLogResult(
            events=[
                api.LogEvent(
                    timestamp=datetime.datetime(2023, 1, 27, 7, 24, 45, tzinfo=tzutc()),
                    message="Test log message",
                    ingestion_time=datetime.datetime(2023, 1, 27, 7, 24, 46, tzinfo=tzutc()),
                    event_id="event-1",
                ),
            ],
            count=1,
            next_token=None,
            log_group=f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}",
            log_stream="session-1",
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "job",
                "logs",
                "--job-id",
                MOCK_JOB_ID,
            ],
        )

        # Verify paginator was called correctly
        boto3_client_mock().get_paginator.assert_called_once_with('list_sessions')
        paginator_mock.paginate.assert_called_once_with(
            farmId=MOCK_FARM_ID, queueId=MOCK_QUEUE_ID, jobId=MOCK_JOB_ID
        )

        # Verify get_session_logs was called with the correct session ID
        mock_get_logs.assert_called_once_with(
            farm_id=MOCK_FARM_ID,
            queue_id=MOCK_QUEUE_ID,
            session_id="session-1",
            limit=100,
            start_time=None,
            end_time=None,
            next_token=None,
            config=ANY,
        )

        # Check output
        assert "Using the only available session: session-1" in result.output
        assert "Test log message" in result.output
        assert result.exit_code == 0


def test_cli_job_logs_with_job_id_multiple_sessions(fresh_deadline_config):
    """
    Test job logs command with job ID when there are multiple sessions.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch.object(api, "get_boto3_client") as boto3_client_mock, patch.object(
        api, "get_session_logs"
    ) as mock_get_logs:
        # Mock the paginator
        paginator_mock = MagicMock()
        boto3_client_mock().get_paginator.return_value = paginator_mock
        
        # Set up the paginator to return multiple sessions
        paginator_mock.paginate.return_value = [
            {"sessions": [
                {"sessionId": "session-1", "endedAt": datetime.datetime(2023, 1, 27, 7, 0, 0, tzinfo=tzutc())},
                {"sessionId": "session-2", "endedAt": datetime.datetime(2023, 1, 27, 8, 0, 0, tzinfo=tzutc())}
            ]}
        ]
        
        # Mock the get_session_logs response
        mock_get_logs.return_value = api.SessionLogResult(
            events=[
                api.LogEvent(
                    timestamp=datetime.datetime(2023, 1, 27, 7, 24, 45, tzinfo=tzutc()),
                    message="Test log message",
                    ingestion_time=datetime.datetime(2023, 1, 27, 7, 24, 46, tzinfo=tzutc()),
                    event_id="event-1",
                ),
            ],
            count=1,
            next_token=None,
            log_group=f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}",
            log_stream="session-2",
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "job",
                "logs",
                "--job-id",
                MOCK_JOB_ID,
            ],
        )

        # Verify paginator was called correctly
        boto3_client_mock().get_paginator.assert_called_once_with('list_sessions')
        paginator_mock.paginate.assert_called_once_with(
            farmId=MOCK_FARM_ID, queueId=MOCK_QUEUE_ID, jobId=MOCK_JOB_ID
        )
        
        # Verify get_session_logs was called with the latest session ID
        mock_get_logs.assert_called_once_with(
            farm_id=MOCK_FARM_ID,
            queue_id=MOCK_QUEUE_ID,
            session_id="session-2",  # Should use the latest session
            limit=100,
            start_time=None,
            end_time=None,
            next_token=None,
            config=ANY,
        )

        # Check output
        assert "Using the latest session: session-2" in result.output
        assert "Test log message" in result.output
        assert result.exit_code == 0


def test_cli_job_logs_with_job_id_no_sessions(fresh_deadline_config):
    """
    Test job logs command with job ID when there are no sessions.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch.object(api, "get_boto3_client") as boto3_client_mock:
        # Mock the paginator
        paginator_mock = MagicMock()
        boto3_client_mock().get_paginator.return_value = paginator_mock
        
        # Set up the paginator to return no sessions
        paginator_mock.paginate.return_value = [{"sessions": []}]

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "job",
                "logs",
                "--job-id",
                MOCK_JOB_ID,
            ],
        )

        # Verify paginator was called correctly
        boto3_client_mock().get_paginator.assert_called_once_with('list_sessions')
        paginator_mock.paginate.assert_called_once_with(
            farmId=MOCK_FARM_ID, queueId=MOCK_QUEUE_ID, jobId=MOCK_JOB_ID
        )

        # Check error message
        assert f"No sessions found for job {MOCK_JOB_ID}" in result.output
        assert result.exit_code != 0


def test_cli_job_logs_with_pagination(fresh_deadline_config):
    """
    Test job logs command with pagination of sessions.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch.object(api, "get_boto3_client") as boto3_client_mock, patch.object(
        api, "get_session_logs"
    ) as mock_get_logs:
        # Mock the paginator
        paginator_mock = MagicMock()
        boto3_client_mock().get_paginator.return_value = paginator_mock
        
        # Set up the paginator to return sessions across multiple pages
        paginator_mock.paginate.return_value = [
            {"sessions": [
                {"sessionId": "session-1", "endedAt": datetime.datetime(2023, 1, 27, 7, 0, 0, tzinfo=tzutc())}
            ]},
            {"sessions": [
                {"sessionId": "session-2", "endedAt": datetime.datetime(2023, 1, 27, 8, 0, 0, tzinfo=tzutc())}
            ]}
        ]
        
        # Mock the get_session_logs response
        mock_get_logs.return_value = api.SessionLogResult(
            events=[
                api.LogEvent(
                    timestamp=datetime.datetime(2023, 1, 27, 8, 0, 0, tzinfo=tzutc()),
                    message="Test log message",
                    ingestion_time=datetime.datetime(2023, 1, 27, 8, 0, 1, tzinfo=tzutc()),
                    event_id="event-1",
                ),
            ],
            count=1,
            next_token=None,
            log_group=f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}",
            log_stream="session-2",
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "job",
                "logs",
                "--job-id",
                MOCK_JOB_ID,
            ],
        )

        # Verify paginator was called correctly
        boto3_client_mock().get_paginator.assert_called_once_with('list_sessions')
        paginator_mock.paginate.assert_called_once_with(
            farmId=MOCK_FARM_ID, queueId=MOCK_QUEUE_ID, jobId=MOCK_JOB_ID
        )
        
        # Verify get_session_logs was called with the latest session ID
        mock_get_logs.assert_called_once_with(
            farm_id=MOCK_FARM_ID,
            queue_id=MOCK_QUEUE_ID,
            session_id="session-2",  # Should use the latest session
            limit=100,
            start_time=None,
            end_time=None,
            next_token=None,
            config=ANY,
        )

        # Check output
        assert "Using the latest session: session-2" in result.output
        assert "Test log message" in result.output
        assert result.exit_code == 0
