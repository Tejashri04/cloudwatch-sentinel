
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
        "error_type": "TimeoutError"
    },
    {
        "service": "InventoryService",
        "level": "ERROR",
        "message": "DynamoDB request timed out",
        "error_type": "TimeoutError"
    },
    {
        "service": "PaymentService",
        "level": "ERROR",
        "message": "Access denied while accessing payment resource",
        "error_type": "AccessDeniedException"
    },
    {
        "service": "OrderService",
        "level": "INFO",
        "message": "Order processed successfully",
        "error_type": ""
    }
]

current_time = int(time.time() * 1000)

log_events = [
    {
        "timestamp": current_time + index * 1000,
        "message": json.dumps(log)
    }
    for index, log in enumerate(sample_logs)
]

response = client.put_log_events(
    logGroupName=LOG_GROUP,
    logStreamName=LOG_STREAM,
    logEvents=log_events
)

print("Sample logs uploaded successfully!")
print("Log events uploaded:", len(log_events))
