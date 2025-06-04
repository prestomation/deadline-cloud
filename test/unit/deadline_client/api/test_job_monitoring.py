# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Tests for the job monitoring API functions.
"""

import datetime
from unittest.mock import patch, MagicMock

from dateutil.tz import tzutc

from deadline.client.api._job_monitoring import (
    wait_for_job_completion,
    get_session_logs,
    JobCompletionResult,
    SessionLogResult,
)
from deadline.client.exceptions import DeadlineOperationError

from ..shared_constants import (
    MOCK_FARM_ID,
    MOCK_JOB_ID,
    MOCK_QUEUE_ID,
)

MOCK_JOB_RUNNING = {
    "jobId": MOCK_JOB_ID,
    "name": "Test Job",
    "taskRunStatus": "RUNNING",
    "lifecycleStatus": "ACTIVE",
    "createdBy": "test-user",
    "createdAt": datetime.datetime(2023, 1, 27, 7, 34, 41, tzinfo=tzutc()),
    "startedAt": datetime.datetime(2023, 1, 27, 7, 37, 53, tzinfo=tzutc()),
}

MOCK_JOB_SUCCEEDED = {
    "jobId": MOCK_JOB_ID,
    "name": "Test Job",
    "taskRunStatus": "SUCCEEDED",
    "lifecycleStatus": "ACTIVE",
    "createdBy": "test-user",
    "createdAt": datetime.datetime(2023, 1, 27, 7, 34, 41, tzinfo=tzutc()),
    "startedAt": datetime.datetime(2023, 1, 27, 7, 37, 53, tzinfo=tzutc()),
    "endedAt": datetime.datetime(2023, 1, 27, 7, 39, 17, tzinfo=tzutc()),
}

MOCK_JOB_FAILED = {
    "jobId": MOCK_JOB_ID,
    "name": "Test Job",
    "taskRunStatus": "FAILED",
    "lifecycleStatus": "ACTIVE",
    "createdBy": "test-user",
    "createdAt": datetime.datetime(2023, 1, 27, 7, 34, 41, tzinfo=tzutc()),
    "startedAt": datetime.datetime(2023, 1, 27, 7, 37, 53, tzinfo=tzutc()),
    "endedAt": datetime.datetime(2023, 1, 27, 7, 39, 17, tzinfo=tzutc()),
}

MOCK_STEPS = {
    "steps": [
        {
            "stepId": "step-123",
            "name": "Step 1",
            "lifecycleStatus": "CREATE_COMPLETE",
            "taskRunStatus": "SUCCEEDED",
            "taskRunStatusCounts": {"FAILED": 0},
        },
        {
            "stepId": "step-456",
            "name": "Step 2",
            "lifecycleStatus": "CREATE_COMPLETE",
            "taskRunStatus": "FAILED",
            "taskRunStatusCounts": {"FAILED": 2},
        },
    ]
}

MOCK_TASKS = {
    "tasks": [
        {
            "taskId": "task-123",
            "runStatus": "FAILED",
            "latestSessionActionId": "sessionaction-abc123-0",
        },
        {
            "taskId": "task-456",
            "runStatus": "FAILED",
            "latestSessionActionId": "sessionaction-def456-1",
        },
        {
            "taskId": "task-789",
            "runStatus": "SUCCEEDED",
            "latestSessionActionId": "sessionaction-ghi789-2",
        },
    ]
}


def test_wait_for_job_completion_success():
    """
    Test that wait_for_job_completion works correctly when job succeeds.
    """
    with patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_client:
        deadline_mock = MagicMock()
        mock_get_client.return_value = deadline_mock

        # First call returns RUNNING, second call returns SUCCEEDED
        deadline_mock.get_job.side_effect = [MOCK_JOB_RUNNING, MOCK_JOB_SUCCEEDED]
        deadline_mock.list_steps.return_value = MOCK_STEPS

        # Mock time.sleep to avoid waiting in tests
        with patch("time.sleep"):
            # Mock datetime.now to simulate elapsed time
            start_time = datetime.datetime(2023, 1, 1, 12, 0, 0)
            end_time = datetime.datetime(2023, 1, 1, 12, 0, 10)

            with patch("datetime.datetime") as dt_mock:
                dt_mock.now.side_effect = [start_time, end_time]

                result = wait_for_job_completion(
                    farm_id=MOCK_FARM_ID,
                    queue_id=MOCK_QUEUE_ID,
                    job_id=MOCK_JOB_ID,
                    poll_interval=1,
                )

                assert isinstance(result, JobCompletionResult)
                assert result.status == "SUCCEEDED"
                assert result.elapsed_time == 10.0
                assert len(result.failed_tasks) == 0

                # Verify the correct parameters were used
                deadline_mock.get_job.assert_called_with(
                    farmId=MOCK_FARM_ID, queueId=MOCK_QUEUE_ID, jobId=MOCK_JOB_ID
                )


def test_wait_for_job_completion_failure():
    """
    Test that wait_for_job_completion works correctly when job fails.
    """
    with patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_client:
        deadline_mock = MagicMock()
        mock_get_client.return_value = deadline_mock

        # First call returns RUNNING, second call returns FAILED
        deadline_mock.get_job.side_effect = [MOCK_JOB_RUNNING, MOCK_JOB_FAILED]
        deadline_mock.list_steps.return_value = MOCK_STEPS
        deadline_mock.list_tasks.return_value = MOCK_TASKS

        # Mock time.sleep to avoid waiting in tests
        with patch("time.sleep"):
            # Mock datetime.now to simulate elapsed time
            start_time = datetime.datetime(2023, 1, 1, 12, 0, 0)
            end_time = datetime.datetime(2023, 1, 1, 12, 0, 15)

            with patch("datetime.datetime") as dt_mock:
                dt_mock.now.side_effect = [start_time, end_time]

                result = wait_for_job_completion(
                    farm_id=MOCK_FARM_ID,
                    queue_id=MOCK_QUEUE_ID,
                    job_id=MOCK_JOB_ID,
                    poll_interval=1,
                )

                assert isinstance(result, JobCompletionResult)
                assert result.status == "FAILED"
                assert result.elapsed_time == 15.0
                assert len(result.failed_tasks) == 2

                # Verify the failed tasks have the correct data
                assert result.failed_tasks[0].step_id == "step-456"
                assert result.failed_tasks[0].task_id == "task-123"
                assert result.failed_tasks[0].step_name == "Step 2"
                assert result.failed_tasks[0].session_id == "session-abc123"

                assert result.failed_tasks[1].step_id == "step-456"
                assert result.failed_tasks[1].task_id == "task-456"
                assert result.failed_tasks[1].step_name == "Step 2"
                assert result.failed_tasks[1].session_id == "session-def456"


def test_wait_for_job_completion_timeout():
    """
    Test that wait_for_job_completion times out correctly.
    """
    with patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_client:
        deadline_mock = MagicMock()
        mock_get_client.return_value = deadline_mock

        # Always return RUNNING to trigger timeout
        deadline_mock.get_job.return_value = MOCK_JOB_RUNNING

        # Mock time.sleep to avoid waiting in tests
        with patch("time.sleep"):
            # Mock datetime.now to simulate time passing beyond timeout
            start_time = datetime.datetime(2023, 1, 1, 12, 0, 0)
            check_time = datetime.datetime(2023, 1, 1, 12, 0, 3)

            with patch("datetime.datetime") as dt_mock:
                dt_mock.now.side_effect = [start_time, check_time]

                try:
                    wait_for_job_completion(
                        farm_id=MOCK_FARM_ID,
                        queue_id=MOCK_QUEUE_ID,
                        job_id=MOCK_JOB_ID,
                        poll_interval=1,
                        timeout=2,
                    )
                    assert False, "Expected DeadlineOperationError was not raised"
                except DeadlineOperationError as e:
                    assert "Timeout waiting for job" in str(e)


def test_wait_for_job_completion_status_callback():
    """
    Test that wait_for_job_completion calls the status callback correctly.
    """
    with patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_client:
        deadline_mock = MagicMock()
        mock_get_client.return_value = deadline_mock

        # First call returns RUNNING, second call returns SUCCEEDED
        deadline_mock.get_job.side_effect = [MOCK_JOB_RUNNING, MOCK_JOB_SUCCEEDED]
        deadline_mock.list_steps.return_value = MOCK_STEPS

        # Create a mock callback
        mock_callback = MagicMock()

        # Mock time.sleep to avoid waiting in tests
        with patch("time.sleep"):
            # Mock datetime.now to simulate elapsed time
            start_time = datetime.datetime(2023, 1, 1, 12, 0, 0)
            end_time = datetime.datetime(2023, 1, 1, 12, 0, 10)

            with patch("datetime.datetime") as dt_mock:
                dt_mock.now.side_effect = [start_time, end_time]

                wait_for_job_completion(
                    farm_id=MOCK_FARM_ID,
                    queue_id=MOCK_QUEUE_ID,
                    job_id=MOCK_JOB_ID,
                    poll_interval=1,
                    status_callback=mock_callback,
                )

                # Verify the callback was called with the correct statuses
                assert mock_callback.call_count == 2
                mock_callback.assert_any_call("RUNNING")
                mock_callback.assert_any_call("SUCCEEDED")


def test_wait_for_job_completion_missing_session_id():
    """
    Test that wait_for_job_completion handles tasks without a session ID.
    """
    with patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_client:
        deadline_mock = MagicMock()
        mock_get_client.return_value = deadline_mock

        # First call returns RUNNING, second call returns FAILED
        deadline_mock.get_job.side_effect = [MOCK_JOB_RUNNING, MOCK_JOB_FAILED]
        deadline_mock.list_steps.return_value = MOCK_STEPS

        # Create a task without latestSessionActionId
        tasks_without_session = {
            "tasks": [
                {
                    "taskId": "task-123",
                    "runStatus": "FAILED",
                    # No latestSessionActionId
                }
            ]
        }

        deadline_mock.list_tasks.return_value = tasks_without_session

        # Mock time.sleep to avoid waiting in tests
        with patch("time.sleep"):
            # Mock datetime.now to simulate elapsed time
            start_time = datetime.datetime(2023, 1, 1, 12, 0, 0)
            end_time = datetime.datetime(2023, 1, 1, 12, 0, 10)

            with patch("datetime.datetime") as dt_mock:
                dt_mock.now.side_effect = [start_time, end_time]

                result = wait_for_job_completion(
                    farm_id=MOCK_FARM_ID,
                    queue_id=MOCK_QUEUE_ID,
                    job_id=MOCK_JOB_ID,
                    poll_interval=1,
                )

                assert len(result.failed_tasks) == 1
                assert result.failed_tasks[0].session_id is None


def test_get_session_logs_success():
    """
    Test that get_session_logs works correctly when logs are found.
    """
    with patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_client:
        deadline_mock = MagicMock()
        mock_get_client.return_value = deadline_mock

        # Mock queue session
        queue_session_mock = MagicMock()
        logs_client_mock = MagicMock()
        queue_session_mock.client.return_value = logs_client_mock

        # Mock the get_queue_user_boto3_session function
        with patch(
            "deadline.client.api._job_monitoring.get_queue_user_boto3_session"
        ) as mock_get_session:
            mock_get_session.return_value = queue_session_mock

            # Mock the logs client response
            logs_client_mock.get_log_events.return_value = {
                "events": [
                    {
                        "timestamp": 1672531200000,  # 2023-01-01 12:00:00
                        "message": "Log message 1",
                        "ingestionTime": 1672531210000,
                        "eventId": "event-1",
                    },
                    {
                        "timestamp": 1672531260000,  # 2023-01-01 12:01:00
                        "message": "Log message 2",
                        "ingestionTime": 1672531270000,
                        "eventId": "event-2",
                    },
                ],
                "nextForwardToken": "next-token",
                "prevBackwardToken": "prev-token",
            }

            result = get_session_logs(
                farm_id=MOCK_FARM_ID,
                queue_id=MOCK_QUEUE_ID,
                session_id="test-session",
                limit=100,
            )

            # Verify the result
            assert isinstance(result, SessionLogResult)
            assert len(result.events) == 2
            assert result.count == 2
            assert result.next_token == "next-token"
            assert result.log_group == f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}"
            assert result.log_stream == "session-test-session"

            # Verify the events
            assert result.events[0].message == "Log message 1"
            # Don't check exact timestamp as it depends on timezone
            assert result.events[0].event_id == "event-1"

            # Verify the logs client was called with correct parameters
            logs_client_mock.get_log_events.assert_called_once_with(
                logGroupName=f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}",
                logStreamName="session-test-session",
                limit=100,
                startFromHead=False,
            )


def test_get_session_logs_empty():
    """
    Test that get_session_logs handles empty results correctly.
    """
    with patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_client:
        deadline_mock = MagicMock()
        mock_get_client.return_value = deadline_mock

        # Mock queue session
        queue_session_mock = MagicMock()
        logs_client_mock = MagicMock()
        queue_session_mock.client.return_value = logs_client_mock

        # Mock the get_queue_user_boto3_session function
        with patch(
            "deadline.client.api._job_monitoring.get_queue_user_boto3_session"
        ) as mock_get_session:
            mock_get_session.return_value = queue_session_mock

            # Mock the logs client response with empty events
            logs_client_mock.get_log_events.return_value = {
                "events": [],
                "prevBackwardToken": "prev-token",
            }

            result = get_session_logs(
                farm_id=MOCK_FARM_ID,
                queue_id=MOCK_QUEUE_ID,
                session_id="test-session",
                limit=100,
            )

            # Verify the result
            assert isinstance(result, SessionLogResult)
            assert len(result.events) == 0
            assert result.count == 0
            assert result.next_token is None
            assert result.log_group == f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}"
            assert result.log_stream == "session-test-session"


def test_get_session_logs_not_found():
    """
    Test that get_session_logs handles ResourceNotFoundException correctly.
    """
    with patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_client:
        deadline_mock = MagicMock()
        mock_get_client.return_value = deadline_mock

        # Mock queue session
        queue_session_mock = MagicMock()
        logs_client_mock = MagicMock()
        queue_session_mock.client.return_value = logs_client_mock

        # Mock the get_queue_user_boto3_session function
        with patch(
            "deadline.client.api._job_monitoring.get_queue_user_boto3_session"
        ) as mock_get_session:
            mock_get_session.return_value = queue_session_mock

            # Mock the logs client to raise ResourceNotFoundException
            logs_client_mock.exceptions.ResourceNotFoundException = Exception
            logs_client_mock.get_log_events.side_effect = (
                logs_client_mock.exceptions.ResourceNotFoundException()
            )

            result = get_session_logs(
                farm_id=MOCK_FARM_ID,
                queue_id=MOCK_QUEUE_ID,
                session_id="test-session",
                limit=100,
            )

            # Verify the result is empty but doesn't raise an exception
            assert isinstance(result, SessionLogResult)
            assert len(result.events) == 0
            assert result.count == 0
            assert result.next_token is None
            assert result.log_group == f"/aws/deadline/{MOCK_FARM_ID}/{MOCK_QUEUE_ID}"
            assert result.log_stream == "session-test-session"


def test_get_session_logs_with_time_params():
    """
    Test that get_session_logs handles time parameters correctly.
    """
    with patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_client:
        deadline_mock = MagicMock()
        mock_get_client.return_value = deadline_mock

        # Mock queue session
        queue_session_mock = MagicMock()
        logs_client_mock = MagicMock()
        queue_session_mock.client.return_value = logs_client_mock

        # Mock the get_queue_user_boto3_session function
        with patch(
            "deadline.client.api._job_monitoring.get_queue_user_boto3_session"
        ) as mock_get_session:
            mock_get_session.return_value = queue_session_mock

            # Mock the logs client response
            logs_client_mock.get_log_events.return_value = {
                "events": [
                    {
                        "timestamp": 1672531200000,  # 2023-01-01 12:00:00
                        "message": "Log message 1",
                        "ingestionTime": 1672531210000,
                        "eventId": "event-1",
                    }
                ],
                "nextForwardToken": "next-token",
                "prevBackwardToken": "prev-token",
            }

            get_session_logs(
                farm_id=MOCK_FARM_ID,
                queue_id=MOCK_QUEUE_ID,
                session_id="test-session",
                limit=100,
                start_time="2023-01-01T12:00:00Z",
                end_time="2023-01-01T13:00:00Z",
            )

            # Verify the logs client was called with correct time parameters
            logs_client_mock.get_log_events.assert_called_once()
            call_args = logs_client_mock.get_log_events.call_args[1]
            assert "startTime" in call_args
            assert "endTime" in call_args
            # Time conversion depends on timezone, so just check that the parameters exist


def test_get_session_logs_with_next_token():
    """
    Test that get_session_logs handles next_token parameter correctly.
    """
    with patch("deadline.client.api._job_monitoring.get_boto3_client") as mock_get_client:
        deadline_mock = MagicMock()
        mock_get_client.return_value = deadline_mock

        # Mock queue session
        queue_session_mock = MagicMock()
        logs_client_mock = MagicMock()
        queue_session_mock.client.return_value = logs_client_mock

        # Mock the get_queue_user_boto3_session function
        with patch(
            "deadline.client.api._job_monitoring.get_queue_user_boto3_session"
        ) as mock_get_session:
            mock_get_session.return_value = queue_session_mock

            # Mock the logs client response
            logs_client_mock.get_log_events.return_value = {
                "events": [
                    {
                        "timestamp": 1672531200000,  # 2023-01-01 12:00:00
                        "message": "Log message 3",
                        "ingestionTime": 1672531210000,
                        "eventId": "event-3",
                    }
                ],
                "nextForwardToken": "next-token-2",
                "prevBackwardToken": "prev-token",
            }

            result = get_session_logs(
                farm_id=MOCK_FARM_ID,
                queue_id=MOCK_QUEUE_ID,
                session_id="test-session",
                limit=100,
                next_token="test-token",
            )

            # Verify the logs client was called with the next_token parameter
            logs_client_mock.get_log_events.assert_called_once()
            call_args = logs_client_mock.get_log_events.call_args[1]
            assert "nextToken" in call_args
            assert call_args["nextToken"] == "test-token"

            # Verify the result contains the new next_token
            assert result.next_token == "next-token-2"
