# CloudWatch Sentinel

**Intelligent Incident Correlation and Alert Noise Reduction for AWS CloudWatch Logs**

CloudWatch Sentinel is a Python-based AWS monitoring prototype that analyzes structured application logs from Amazon CloudWatch Logs, identifies related failures across services, groups them into incidents, and tracks incident recovery.

It helps reduce alert noise by correlating repeated failures, detecting duplicate events, maintaining incident state, and sending notifications for important incidents.

The project demonstrates serverless AWS architecture, event-driven processing, persistent incident management, automated recovery evaluation, and CI/CD deployment.

## Key Features

- **AWS CloudWatch Integration:** Collect structured log events from Amazon CloudWatch Logs using Boto3.
- **Structured Log Parsing:** Parse JSON-formatted log events.
- **Error Classification:** Identify timeouts, permission failures, throttling, connectivity issues, and application errors.
- **Incident Correlation:** Group related failures using incident fingerprints.
- **Severity Classification:** Assign severity levels to detected incidents.
- **Root-Cause Hints:** Generate suggestions to assist incident investigation.
- **Duplicate Event Detection:** Prevent repeated processing of the same log events.
- **Persistent Incident Management:** Store incident information in Amazon DynamoDB.
- **Alert Noise Reduction:** Group related failures rather than creating separate alerts for every matching event.
- **SNS Notifications:** Send incident notifications through Amazon Simple Notification Service.
- **Notification Reliability:** Use a DynamoDB notification outbox to track delivery attempts and retry pending notifications.
- **Automated Recovery Evaluation:** Periodically evaluate incident recovery.
- **Heartbeat Monitoring:** Use a Windows Scheduled Task to periodically upload heartbeat events.
- **Automated Testing:** Validate application functionality using pytest.
- **Code Quality:** Enforce Python code quality using Ruff.
- **CI/CD:** Build and deploy the AWS SAM application using GitHub Actions and AWS OIDC authentication.

## Architecture

```text
Sample Application Logs
          |
          v
Amazon CloudWatch Logs
          |
          v
CloudWatch Logs Subscription Filter
          |
          v
Incident Processor Lambda
          |
          +----------------------+
          |                      |
          v                      v
DynamoDB Incident Table   DynamoDB Processed Events Table
          |
          v
DynamoDB Notification Outbox
          |
          v
Notification Dispatcher Lambda
          |
          v
Amazon SNS
          |
          v
Email Notifications


EventBridge (Every 5 Minutes)
          |
          +-----------------------------+
          |                             |
          v                             v
Recovery Evaluator Lambda     Notification Dispatcher Lambda
          |
          v
Evaluate Incident Recovery
```

## Technology Stack

| Category | Technologies |
|---|---|
| Programming Language | Python 3.12 |
| AWS Monitoring | Amazon CloudWatch Logs |
| Serverless | AWS Lambda |
| Infrastructure as Code | AWS SAM, AWS CloudFormation |
| Database | Amazon DynamoDB |
| Notifications | Amazon SNS |
| Scheduling | Amazon EventBridge |
| AWS SDK | Boto3 |
| Testing | pytest, moto |
| Code Quality | Ruff |
| CI/CD | GitHub Actions |
| Authentication | AWS IAM, GitHub OIDC |
| Version Control | Git and GitHub |

## How It Works

1. Structured sample log events are uploaded to Amazon CloudWatch Logs.
2. A CloudWatch Logs subscription filter forwards log events to the Incident Processor Lambda.
3. The Lambda decodes and processes the incoming log events.
4. The classifier identifies error categories and severity.
5. The correlator groups related failures using incident fingerprints.
6. DynamoDB stores incident information and processed event identifiers.
7. A notification outbox records notifications that need to be delivered.
8. The Notification Dispatcher Lambda publishes pending notifications to SNS.
9. EventBridge periodically triggers the Recovery Evaluator Lambda.
10. The Recovery Evaluator checks whether previously open incidents have recovered and updates their state.

## AWS Resources

The SAM template provisions the following resources:

| AWS Resource | Purpose |
|---|---|
| CloudWatch Logs | Receives structured log events |
| Incident Processor Lambda | Processes logs and identifies incidents |
| Recovery Evaluator Lambda | Evaluates incident recovery |
| Notification Dispatcher Lambda | Delivers pending notifications |
| Incident DynamoDB Table | Stores incident state |
| Processed Events DynamoDB Table | Tracks processed events and supports deduplication |
| Notification Outbox DynamoDB Table | Tracks notification delivery and retries |
| Amazon SNS Topic | Distributes incident notifications |
| Amazon EventBridge | Schedules recovery evaluation and notification dispatch |

## Incident Detection Example

Suppose two services encounter timeout errors while accessing a dependency:

- `OrderService`
- `InventoryService`

CloudWatch Sentinel groups these related failures under the same incident fingerprint.

A separate permission failure from `PaymentService` is classified as another incident.

### Example Output

```text
Connecting to AWS CloudWatch...
Reading logs from: /cloudwatch-sentinel/application

Total CloudWatch log events fetched: 4
Valid structured events: 4

========== INCIDENT ANALYSIS ==========

Category: TIMEOUT
Severity: HIGH
Fingerprint: TIMEOUT:timeouterror
Affected services: InventoryService, OrderService
Event count: 2
Root cause hint: Check dependency latency, network delays, and timeout settings.

Category: PERMISSION
Severity: HIGH
Fingerprint: PERMISSION:accessdeniedexception
Affected services: PaymentService
Event count: 1
Root cause hint: Check IAM permissions, resource policies, and credentials.

========== ALERT STATUS ==========

{'new': [], 'ongoing': ['PERMISSION:accessdeniedexception', 'TIMEOUT:timeouterror']}

Incident analysis completed.
```

*The output is an example from a successful project run. Actual incident status depends on previously stored state.*

## Incident Recovery

CloudWatch Sentinel tracks incident state and detects recovery.

The local state tracker uses the following statuses:

- **NEW:** An incident is detected for the first time or reappears after recovery.
- **ONGOING:** A previously open incident remains active.
- **RECOVERED:** An incident has been absent for the configured recovery threshold.

The default recovery threshold is two consecutive analysis runs without the incident.

The AWS implementation uses DynamoDB to persist incident information and a scheduled Recovery Evaluator Lambda to evaluate recovery.

## Heartbeat Monitoring

The project includes a PowerShell script named `heartbeat_task.ps1`.

It runs the following command:

```powershell
python send_sample_logs.py --heartbeat-only
```

The script uploads a heartbeat event to the configured CloudWatch log group and records execution output in:

```text
data/heartbeat-task.log
```

A Windows Scheduled Task named `CloudWatch Sentinel Heartbeat` can execute this script periodically.

The heartbeat helps demonstrate scheduled monitoring and provides a recurring test event for the prototype.

## Project Structure

```text
cloudwatch-sentinel/
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
│
├── src/
│   └── sentinel/
│       ├── __init__.py
│       ├── alert_manager.py
│       ├── classifier.py
│       ├── cloudwatch.py
│       ├── correlator.py
│       ├── demo.py
│       ├── dynamodb_store.py
│       ├── lambda_handler.py
│       ├── notification_dispatcher.py
│       ├── recovery_handler.py
│       └── state.py
│
├── tests/
│   ├── test_alert_manager.py
│   ├── test_classifier.py
│   ├── test_cloudwatch.py
│   ├── test_correlator.py
│   ├── test_dynamodb_store.py
│   ├── test_lambda_handler.py
│   ├── test_notification_dispatcher.py
│   ├── test_recovery_handler.py
│   └── test_state.py
│
├── heartbeat_task.ps1
├── pyproject.toml
├── recovery-response.json
├── run_cloudwatch.py
├── samconfig.toml
├── send_sample_logs.py
├── template.yaml
├── test-recovery-filter.json
├── test-recovery-item.json
├── test-recovery-key.json
├── README.md
└── .gitignore
```

Runtime data, virtual environments, and SAM build artifacts are excluded from version control.

## Prerequisites

Before running the project, make sure you have:

- Python 3.12
- AWS CLI
- AWS SAM CLI
- An AWS account
- AWS authentication configured securely
- Git
- Access to the configured CloudWatch log group
- Appropriate IAM permissions for the required AWS resources

The project uses the following defaults:

```text
AWS Region: ap-south-1
CloudWatch Log Group: /cloudwatch-sentinel/application
```

## Setup and Installation

### 1. Clone the Repository

```powershell
git clone https://github.com/Tejashri04/cloudwatch-sentinel.git
cd cloudwatch-sentinel
```

### 2. Create a Virtual Environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
python -m pip install boto3 pytest ruff moto
```

### 4. Configure AWS Authentication

Authenticate using an approved AWS CLI authentication method.

For example:

```powershell
aws login --region ap-south-1
```

Verify your AWS identity:

```powershell
aws sts get-caller-identity
```

Never store AWS access keys, secret keys, or other credentials in source code or GitHub.

### 5. Configure the CloudWatch Log Group

The application uses:

```text
Region: ap-south-1
Log Group: /cloudwatch-sentinel/application
```

Ensure the log group exists and the authenticated AWS identity has the necessary CloudWatch permissions.

## Running the Project Locally

### Analyze CloudWatch Logs

```powershell
python run_cloudwatch.py
```

This fetches log events, classifies errors, correlates incidents, and reports incident status.

### Send Sample Logs

```powershell
python send_sample_logs.py
```

This uploads sample structured log events to CloudWatch.

To upload only a heartbeat event:

```powershell
python send_sample_logs.py --heartbeat-only
```

These operations interact with AWS and may incur charges depending on usage and applicable AWS pricing.

## AWS Deployment Using SAM

The project uses AWS Serverless Application Model (SAM) to define and deploy its serverless infrastructure.

### Validate the SAM Template

```powershell
sam validate --lint
```

### Build the Application

```powershell
sam build
```

### Deploy

The configured GitHub Actions workflow performs the deployment.

The workflow uses:

- GitHub Actions
- AWS OIDC authentication
- AWS IAM deployment role
- AWS SAM CLI
- AWS CloudFormation

Deployment is manually triggered through GitHub Actions using `workflow_dispatch`.

Configure the following GitHub repository variables:

| Variable | Purpose |
|---|---|
| `AWS_ROLE_ARN` | IAM role assumed through GitHub OIDC |
| `AWS_REGION` | AWS deployment region |
| `SAM_STACK_NAME` | CloudFormation stack name |

The IAM role must have the permissions required to deploy the SAM application.

## CI/CD Pipeline

The GitHub Actions workflow automates the build and deployment process.

```text
GitHub Repository
        |
        v
Manual Workflow Trigger
        |
        v
GitHub Actions Runner
        |
        v
AWS OIDC Authentication
        |
        v
AWS IAM Deployment Role
        |
        v
SAM Build
        |
        v
SAM Deploy
        |
        v
AWS CloudFormation Stack
        |
        v
AWS Serverless Resources
```

The deployment workflow is manually triggered to provide control over AWS deployments.

## Running Tests

Run the complete test suite:

```powershell
python -m pytest -v
```

The project currently has **50 passing tests** covering:

- Error classification
- Incident correlation
- CloudWatch integration
- Alert management
- Incident state tracking
- Lambda event processing
- DynamoDB persistence and deduplication
- Notification dispatch and retries
- Recovery evaluation

### Check Code Quality

```powershell
python -m ruff check .
```

The project passes Ruff checks.

### Validate and Build SAM

```powershell
sam validate --lint
sam build
```

The SAM template validates successfully and the application builds successfully.

## Security and Reliability

The project incorporates several reliability and security practices:

- AWS IAM roles and least-privilege permissions.
- GitHub OIDC authentication instead of storing long-lived AWS credentials in GitHub.
- DynamoDB-based persistent incident storage.
- Processed event tracking to reduce duplicate processing.
- Notification outbox to support reliable notification delivery.
- Retry and attempt tracking for notification failures.
- DynamoDB TTL for processed event records.
- CloudWatch and Lambda logging for operational visibility.

## Learning Outcomes

This project demonstrates practical experience with:

- AWS CloudWatch Logs and Boto3.
- AWS Lambda and event-driven architecture.
- AWS SAM and infrastructure as code.
- DynamoDB data persistence and transactions.
- Amazon SNS notifications.
- Amazon EventBridge scheduling.
- Python application development.
- Cross-service incident correlation.
- Duplicate event detection and alert noise reduction.
- Automated recovery evaluation.
- pytest and moto testing.
- Ruff code quality checks.
- GitHub Actions CI/CD.
- AWS IAM and GitHub OIDC authentication.

## Future Enhancements

- Advanced service dependency mapping.
- Improved root-cause analysis.
- Incident dashboards and visualization.
- Configurable alert policies and notification channels.
- More advanced incident analytics.
- Additional observability integrations.

## Author

**Tejashri**

GitHub: https://github.com/Tejashri04

Project Repository: https://github.com/Tejashri04/cloudwatch-sentinel
