# CloudWatch Sentinel

Intelligent incident correlation and alert noise reduction for AWS.

## Goals

- Classify application errors from structured logs.
- Identify related failures across multiple services.
- Group repeated errors into incidents.
- Reduce duplicate alerts.
- Provide useful root-cause hints.
- Verify recovery after failures stop.

## Technology

- Python 3.12
- boto3
- pytest
- Ruff

## Development

The initial incident classification engine is developed and tested locally
before AWS services are introduced.