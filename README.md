# CloudWatch Sentinel

**Intelligent Incident Correlation and Alert Noise Reduction for AWS CloudWatch Logs**

CloudWatch Sentinel is a Python-based monitoring project that analyzes structured application logs from Amazon CloudWatch Logs, identifies related failures across multiple services, groups them into incidents, and tracks incident recovery.

The project aims to reduce duplicate alerts and provide actionable root-cause hints to help developers investigate application failures.

## Key Features

- **AWS CloudWatch Integration:** Fetch application logs from AWS CloudWatch Logs using Boto3.
- **Structured Log Parsing:** Parse JSON-formatted log events for analysis.
- **Error Classification:** Categorize errors such as timeouts, permission failures, throttling, connectivity issues, and application errors.
- **Incident Correlation:** Group related errors across multiple services using incident fingerprints.
- **Severity Classification:** Assign severity levels to detected errors.
- **Root-Cause Hints:** Provide suggestions to help investigate potential causes of incidents.
- **Incident State Tracking:** Identify new and ongoing incidents and detect recovery.
- **Alert Noise Reduction:** Group repeated related failures to avoid treating every matching log event as a separate incident.
- **Automated Testing:** Validate core functionality with pytest.
- **Code Quality:** Use Ruff to check Python code.

## Architecture

```text
Application Services
        |
        v
Structured Application Logs
        |
        v
Amazon CloudWatch Logs
        |
        v
CloudWatch Log Fetcher (Boto3)
        |
        v
JSON Log Parser
        |
        v
Error Classifier
        |
        v
Incident Correlator
        |
        v
Incident State Tracking
        |
        v
Alert Status and Root-Cause Hints
        |
        v
Console Output
```

## Technology Stack

- Python 3.12
- Amazon CloudWatch Logs
- AWS SDK for Python (Boto3)
- pytest
- Ruff
- Git and GitHub

## Project Structure

```text
cloudwatch-sentinel/
├── data/
│   └── incidents.json
├── src/
│   └── sentinel/
│       ├── alert_manager.py
│       ├── classifier.py
│       ├── cloudwatch.py
│       ├── correlator.py
│       ├── demo.py
│       └── state.py
├── tests/
│   ├── test_alert_manager.py
│   ├── test_classifier.py
│   ├── test_cloudwatch.py
│   ├── test_correlator.py
│   └── test_state.py
├── run_cloudwatch.py
├── send_sample_logs.py
├── README.md
└── .gitignore
```

## How It Works

1. Connects to Amazon CloudWatch Logs.
2. Fetches structured application log events from the configured log group.
3. Parses valid JSON events.
4. Classifies errors by category and severity.
5. Groups related failures using incident fingerprints.
6. Identifies affected services and generates root-cause hints.
7. Tracks incident states across executions.
8. Reports new, ongoing, and recovered incidents.

Incident recovery is detected after an incident is absent for two consecutive analysis runs.

## Example Scenario

Suppose two services encounter timeout errors while accessing a dependency:

- `OrderService`
- `InventoryService`

Instead of treating the two matching failures as unrelated incidents, CloudWatch Sentinel groups them under the same incident fingerprint.

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

{'new': [], 'ongoing': ['PERMISSION:accessdeniedexception', 'TIMEOUT:timeouterror'], 'recovered': []}

Incident analysis completed.
```

*The output above is an example from a successful project run. Alert status depends on the previously stored incident state.*

## Prerequisites

Before running the project, make sure you have:

- Python 3.12 or a compatible Python version.
- AWS CLI installed.
- An AWS account with access to CloudWatch Logs.
- AWS credentials configured securely for Boto3.
- Access to the `/cloudwatch-sentinel/application` log group in the `ap-south-1` region.

## Setup and Installation

### 1. Clone the repository

```bash
git clone https://github.com/Tejashri04/cloudwatch-sentinel.git
cd cloudwatch-sentinel
```

### 2. Create a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install boto3 "botocore[crt]" pytest ruff
```

### 4. Configure AWS authentication

Configure AWS authentication using an approved AWS CLI authentication method. For example, if AWS CLI login is available for your environment:

```powershell
aws login --region ap-south-1
```

Verify that AWS authentication works:

```powershell
aws sts get-caller-identity
```

Do not put AWS access keys or secret credentials in your source code or Git repository.

### 5. Configure the CloudWatch log group

The application currently reads from:

```text
Region: ap-south-1
Log group: /cloudwatch-sentinel/application
```

Ensure that the log group exists and that your AWS identity has permission to read its log events.

## Running the Project

### Analyze CloudWatch logs

```powershell
python run_cloudwatch.py
```

The application fetches logs, identifies incidents, and prints incident details and alert status.

### Send sample logs

To populate the configured CloudWatch log stream with sample events, run:

```powershell
python send_sample_logs.py
```

This operation writes events to AWS and may incur charges depending on your usage and AWS pricing. Run it only when you intend to upload the sample events.

## Running Tests

Run the complete test suite:

```powershell
python -m pytest -v
```

The project currently has **25 passing tests** covering classification, incident correlation, CloudWatch integration, alert management, and incident state tracking.

### Check Code Quality

```powershell
python -m ruff check .
```

The current code passes Ruff checks.

## Incident State Tracking

CloudWatch Sentinel maintains incident state in:

```text
data/incidents.json
```

The state tracker distinguishes between:

- **NEW:** An incident is detected for the first time or reappears after being resolved.
- **ONGOING:** A previously open incident remains active.
- **RECOVERED:** An open incident has been absent for the configured recovery threshold.

The default recovery threshold is two consecutive analysis runs without the incident.

The JSON state file persists between executions, allowing the application to track incidents across runs.

## Future Enhancements

- Amazon SNS notifications for important incidents.
- More advanced cross-service dependency correlation.
- Configurable log lookback windows and incident thresholds.
- Improved root-cause analysis.
- Dashboards for incident history and service health.
- GitHub Actions automation for testing and deployment.

## Learning Outcomes

This project demonstrates practical experience with:

- AWS CloudWatch Logs and Boto3 integration.
- Python application design and modular programming.
- Log parsing and error classification.
- Cross-service incident correlation.
- Persistent state management and recovery detection.
- Automated testing with pytest.
- Code-quality checks with Ruff.
- Git and GitHub project management.

## Author

**Tejashri**

GitHub: https://github.com/Tejashri04