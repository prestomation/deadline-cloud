# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Tests for the CLI job commands.
"""

import datetime
import json
import os
from typing import Dict, List
import pytest
from pathlib import Path
import sys
from unittest.mock import ANY, MagicMock, patch, call

import boto3  # type: ignore[import]
from botocore.exceptions import ClientError  # type: ignore[import]
from click.testing import CliRunner
from dateutil.tz import tzutc  # type: ignore[import]

from deadline.client import api, config
from deadline.client.cli import main
from deadline.client.cli._groups import job_group
from deadline.client.cli._groups.job_group import _get_summary_of_files_to_download_message
from deadline.job_attachments.models import (
    FileConflictResolution,
    JobAttachmentS3Settings,
    PathFormat,
)
from deadline.job_attachments.progress_tracker import (
    DownloadSummaryStatistics,
)
from ..api.test_job_bundle_submission import (
    MOCK_GET_QUEUE_RESPONSE,
)
from ..shared_constants import (
    MOCK_FARM_ID,
    MOCK_JOB_ID,
    MOCK_QUEUE_ID,
    MOCK_FLEET_ID,
    MOCK_WORKER_ID,
)

MOCK_JOBS_LIST = [
    {
        "jobId": "job-aaf4cdf8aae242f58fb84c5bb19f199b",
        "name": "CLI Job",
        "taskRunStatus": "RUNNING",
        "lifecycleStatus": "SUCCEEDED",
        "createdBy": "b801f3c0-c071-70bc-b869-6804bc732408",
        "createdAt": datetime.datetime(2023, 1, 27, 7, 34, 41, tzinfo=tzutc()),
        "startedAt": datetime.datetime(2023, 1, 27, 7, 37, 53, tzinfo=tzutc()),
        "endedAt": datetime.datetime(2023, 1, 27, 7, 39, 17, tzinfo=tzutc()),
        "priority": 50,
    },
    {
        "jobId": "job-0d239749fa05435f90263b3a8be54144",
        "name": "CLI Job",
        "taskRunStatus": "COMPLETED",
        "lifecycleStatus": "SUCCEEDED",
        "createdBy": "b801f3c0-c071-70bc-b869-6804bc732408",
        "createdAt": datetime.datetime(2023, 1, 27, 7, 24, 22, tzinfo=tzutc()),
        "startedAt": datetime.datetime(2023, 1, 27, 7, 27, 6, tzinfo=tzutc()),
        "endedAt": datetime.datetime(2023, 1, 27, 7, 29, 51, tzinfo=tzutc()),
        "priority": 50,
    },
]

MOCK_SESSIONS_LIST = [
    {
        "sessionId": "session-1",
        "fleetId": MOCK_FLEET_ID,
        "workerId": MOCK_WORKER_ID,
        "startedAt": datetime.datetime(2023, 1, 27, 7, 24, 22, tzinfo=tzutc()),
        "lifecycleStatus": "ENDED",
        "endedAt": datetime.datetime(2023, 1, 27, 7, 25, 22, tzinfo=tzutc()),
    },
]

MOCK_SESSION_ACTIONS_LIST = [
    {
        "sessionActionId": "sessionaction-1-0",
        "status": "SUCCEEDED",
        "startedAt": datetime.datetime(2023, 1, 27, 7, 24, 45, tzinfo=tzutc()),
        "endedAt": datetime.datetime(2023, 1, 27, 7, 25, 15, tzinfo=tzutc()),
        "progressPercent": 100.0,
        "definition": {
            "taskRun": {
                "taskId": "task-0a0ac395f3ed4d61bda7019874b1f384-0",
                "stepId": "step-0a0ac395f3ed4d61bda7019874b1f384",
            }
        },
    },
]

MOCK_STEP = {
    "stepId": "step-0a0ac395f3ed4d61bda7019874b1f384",
    "name": "Step Name",
    "lifecycleStatus": "CREATE_COMPLETE",
    "taskRunStatus": "SUCCEEDED",
    "taskRunStatusCounts": {
        "PENDING": 0,
        "READY": 0,
        "RUNNING": 0,
        "ASSIGNED": 0,
        "STARTING": 0,
        "SCHEDULED": 0,
        "INTERRUPTING": 0,
        "SUSPENDED": 0,
        "CANCELED": 0,
        "FAILED": 0,
        "SUCCEEDED": 1,
    },
    "createdAt": datetime.datetime(2023, 1, 27, 7, 14, 41, tzinfo=tzutc()),
    "createdBy": "a4a874f8-10b1-70d6-e763-a0e3822893b0",
    "startedAt": datetime.datetime(2023, 1, 27, 7, 24, 45, tzinfo=tzutc()),
    "endedAt": datetime.datetime(2023, 1, 27, 7, 25, 15, tzinfo=tzutc()),
}

MOCK_TASK = {
    "taskId": "task-0a0ac395f3ed4d61bda7019874b1f384-2",
    "createdAt": datetime.datetime(2023, 1, 27, 7, 14, 41, tzinfo=tzutc()),
    "createdBy": "a4a874f8-10b1-70d6-e763-a0e3822893b0",
    "runStatus": "SUCCEEDED",
    "failureRetryCount": 0,
    "parameters": {},
    "startedAt": datetime.datetime(2023, 1, 27, 7, 24, 45, tzinfo=tzutc()),
    "endedAt": datetime.datetime(2023, 1, 27, 7, 25, 15, tzinfo=tzutc()),
    "latestSessionActionId": "sessionaction-1-0",
}

os.environ["AWS_ENDPOINT_URL_DEADLINE"] = "https://fake-endpoint"


def test_cli_job_list(fresh_deadline_config):
    """
    Confirm that the CLI interface prints out the expected list of
    jobs, given mock data.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch.object(api._session, "get_boto3_session") as session_mock:
        session_mock().client("deadline").search_jobs.return_value = {
            "jobs": MOCK_JOBS_LIST,
            "totalResults": 12,
            "itemOffset": len(MOCK_JOBS_LIST),
        }

        runner = CliRunner()
        result = runner.invoke(main, ["job", "list"])

        assert (
            result.output
            == """Displaying 2 of 12 Jobs starting at 0

- name: CLI Job
  jobId: job-aaf4cdf8aae242f58fb84c5bb19f199b
  taskRunStatus: RUNNING
  startedAt: 2023-01-27 07:37:53+00:00
  endedAt: 2023-01-27 07:39:17+00:00
  createdBy: b801f3c0-c071-70bc-b869-6804bc732408
  createdAt: 2023-01-27 07:34:41+00:00
- name: CLI Job
  jobId: job-0d239749fa05435f90263b3a8be54144
  taskRunStatus: COMPLETED
  startedAt: 2023-01-27 07:27:06+00:00
  endedAt: 2023-01-27 07:29:51+00:00
  createdBy: b801f3c0-c071-70bc-b869-6804bc732408
  createdAt: 2023-01-27 07:24:22+00:00

"""
        )
        assert result.exit_code == 0


def test_cli_job_list_explicit_farm_and_queue_id(fresh_deadline_config):
    """
    Confirm that the CLI interface prints out the expected list of
    jobs, given mock data.
    """
    with patch.object(api._session, "get_boto3_session") as session_mock:
        session_mock().client("deadline").search_jobs.return_value = {
            "jobs": MOCK_JOBS_LIST,
            "totalResults": 12,
            "itemOffset": len(MOCK_JOBS_LIST),
        }

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["job", "list", "--farm-id", MOCK_FARM_ID, "--queue-id", MOCK_QUEUE_ID],
        )

        assert (
            result.output
            == """Displaying 2 of 12 Jobs starting at 0

- name: CLI Job
  jobId: job-aaf4cdf8aae242f58fb84c5bb19f199b
  taskRunStatus: RUNNING
  startedAt: 2023-01-27 07:37:53+00:00
  endedAt: 2023-01-27 07:39:17+00:00
  createdBy: b801f3c0-c071-70bc-b869-6804bc732408
  createdAt: 2023-01-27 07:34:41+00:00
- name: CLI Job
  jobId: job-0d239749fa05435f90263b3a8be54144
  taskRunStatus: COMPLETED
  startedAt: 2023-01-27 07:27:06+00:00
  endedAt: 2023-01-27 07:29:51+00:00
  createdBy: b801f3c0-c071-70bc-b869-6804bc732408
  createdAt: 2023-01-27 07:24:22+00:00

"""
        )
        assert result.exit_code == 0


def test_cli_job_list_override_profile(fresh_deadline_config):
    """
    Confirms that the --profile option overrides the option to boto3.Session.
    """
    # set the farm id for the overridden profile
    config.set_setting("defaults.aws_profile_name", "NonDefaultProfileName")
    config.set_setting("defaults.farm_id", "farm-overriddenid")
    config.set_setting("defaults.queue_id", "queue-overriddenid")
    config.set_setting("defaults.aws_profile_name", "DifferentProfileName")

    with patch.object(boto3, "Session") as session_mock:
        session_mock().client("deadline").search_jobs.return_value = {
            "jobs": MOCK_JOBS_LIST,
            "totalResults": 12,
            "nextPage": len(MOCK_JOBS_LIST),
        }
        session_mock.reset_mock()

        runner = CliRunner()
        result = runner.invoke(main, ["job", "list", "--profile", "NonDefaultProfileName"])

        assert result.exit_code == 0
        session_mock.assert_called_once_with(profile_name="NonDefaultProfileName")
        session_mock().client().search_jobs.assert_called_once_with(
            farmId="farm-overriddenid",
            queueIds=["queue-overriddenid"],
            itemOffset=0,
            pageSize=5,
            sortExpressions=[{"fieldSort": {"name": "CREATED_AT", "sortOrder": "DESCENDING"}}],
        )


def test_cli_job_list_no_farm_id(fresh_deadline_config):
    with patch.object(api._session, "get_boto3_session") as session_mock:
        session_mock().client("deadline").search_jobs.return_value = {
            "jobs": MOCK_JOBS_LIST,
            "totalResults": 12,
            "nextPage": len(MOCK_JOBS_LIST),
        }

        runner = CliRunner()
        result = runner.invoke(main, ["job", "list"])

        assert "Missing '--farm-id' or default Farm ID configuration" in result.output
        assert result.exit_code != 0


def test_cli_job_list_no_queue_id(fresh_deadline_config):
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)

    with patch.object(api._session, "get_boto3_session") as session_mock:
        session_mock().client("deadline").search_jobs.return_value = {
            "jobs": MOCK_JOBS_LIST,
            "totalResults": 12,
            "nextPage": len(MOCK_JOBS_LIST),
        }

        runner = CliRunner()
        result = runner.invoke(main, ["job", "list"])

        assert "Missing '--queue-id' or default Queue ID configuration" in result.output
        assert result.exit_code != 0


def test_cli_job_list_client_error(fresh_deadline_config):
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch.object(api._session, "get_boto3_session") as session_mock:
        session_mock().client("deadline").search_jobs.side_effect = ClientError(
            {"Error": {"Message": "A botocore client error"}}, "client error"
        )

        runner = CliRunner()
        result = runner.invoke(main, ["job", "list"])

        assert "Failed to get Jobs" in result.output
        assert "A botocore client error" in result.output
        assert result.exit_code != 0


def test_cli_job_get(fresh_deadline_config):
    """
    Confirm that the CLI interface prints out the expected job, given mock data.
    """

    with patch.object(api._session, "get_boto3_session") as session_mock:
        session_mock().client("deadline").get_job.return_value = MOCK_JOBS_LIST[0]

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "job",
                "get",
                "--farm-id",
                MOCK_FARM_ID,
                "--queue-id",
                MOCK_QUEUE_ID,
                "--job-id",
                str(MOCK_JOBS_LIST[0]["jobId"]),
            ],
        )

        assert (
            result.output
            == """jobId: job-aaf4cdf8aae242f58fb84c5bb19f199b
name: CLI Job
taskRunStatus: RUNNING
lifecycleStatus: SUCCEEDED
createdBy: b801f3c0-c071-70bc-b869-6804bc732408
createdAt: 2023-01-27 07:34:41+00:00
startedAt: 2023-01-27 07:37:53+00:00
endedAt: 2023-01-27 07:39:17+00:00
priority: 50

"""
        )
        session_mock().client("deadline").get_job.assert_called_once_with(
            farmId=MOCK_FARM_ID, queueId=MOCK_QUEUE_ID, jobId=MOCK_JOBS_LIST[0]["jobId"]
        )
        assert result.exit_code == 0


def test_cli_job_logs_with_session_id(fresh_deadline_config):
    """
    Test job logs command with explicit session ID.
    """
    config.set_setting("defaults.farm_id", MOCK_FARM_ID)
    config.set_setting("defaults.queue_id", MOCK_QUEUE_ID)

    with patch.object(api, "get_session_logs") as mock_get_logs:
        # Mock the API response
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
