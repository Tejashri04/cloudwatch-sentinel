
"""Upload sample application logs or a heartbeat to CloudWatch."""

import argparse
import json
import time

import boto3

REGION = "ap-south-1"
LOG_GROUP = "/cloudwatch-sentinel/application"
LOG_STREAM = "order-service-stream"

client = boto3.client("logs", region_name=REGION)

sample_logs = [
    {
        "service": "OrderService",
        "level": "ERROR",
        "message": "DynamoDB request timed out",
        "error_type": "TimeoutError",
    },
    {
        "service": "InventoryService",
        "level": "ERROR",
        "message": "DynamoDB request timed out",
        "error_type": "TimeoutError",
    },
    {
        "service": "PaymentService",
        "level": "ERROR",
        "message": "Access denied while accessing payment resource",
        "error_type": "AccessDeniedException",
    },
    {
        "service": "OrderService",
        "level": "INFO",
        "message": "Order processed successfully",
        "error_type": "",
    },
]


def create_heartbeat():
    """Create a simulated application heartbeat."""

    return {
        "service": "OrderService",
        "level": "INFO",
        "event_type": "HEARTBEAT",
        "message": "Application health check successful",
        "error_type": "",
    }


def upload_logs(logs):
    """Upload log events to CloudWatch."""

    current_time = int(time.time() * 1000)

    log_events = [
        {
            "timestamp": current_time + index,
            "message": json.dumps(log),
        }
        for index, log in enumerate(logs)
    ]

    client.put_log_events(
        logGroupName=LOG_GROUP,
        logStreamName=LOG_STREAM,
        logEvents=log_events,
    )

    print("Logs uploaded successfully!")
    print("Log events uploaded:", len(log_events))


def main():
    parser = argparse.ArgumentParser(
        description="Send sample logs or heartbeat to CloudWatch."
    )

    parser.add_argument(
        "--heartbeat-only",
        action="store_true",
        help="Send only a heartbeat event.",
    )

    args = parser.parse_args()

    if args.heartbeat_only:
        upload_logs([create_heartbeat()])
    else:
        upload_logs(sample_logs)


if __name__ == "__main__":
    main()
