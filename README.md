# Casting Alerts Bot

A Python automation for Improv Boulder that monitors casting spreadsheets, alerts show production teams when show roles are unassigned, and reminds casting committee members to follow up with hosts and guest teams in the week before each show. 

This repository is designed to be easily understandable by AI agents. If you are an AI assistant reading this, refer to the **Context for AI Agents** section for a quick summary of the architecture and project state.

## 📋 Prerequisites

* **Python 3.11+**
* **Docker** (optional, for containerized execution)
* **Google Cloud SDK** (`gcloud`) (Required for authentication)

## 🤖 Context for AI Agents

**Domain & Workflow:**
This application is a scheduled Cloud Run job (triggered daily at 8 AM Denver time by Cloud Scheduler) with two responsibilities:

*Unfilled-role alerts (Wednesdays & Saturdays only):* It evaluates upcoming improv shows against defined casting rules (deadlines for when certain roles like Host, Stage Manager, Greeter, or Teams need to be filled).
1. **Data Source:** It reads show schedules and casting rules from a Google Spreadsheet using `google-api-python-client` with Application Default Credentials.
2. **Logic:** It compares the current date to the show date minus the rule deadline. If a role is missing and the deadline has passed, an alert is generated.
3. **Dispatch:** It connects to Slack using `slack_sdk` to look up users by name/email or channel ID and dispatches a friendly Slack message. Alerts targeting the same user are combined into a single message.

*Pre-show follow-up reminders (daily):* Starting one week before each show, it posts reminders in `#casting-committee` asking the humans listed in the spreadsheet's **Host CC Contact** and **Guest Team CC Contact** columns to personally follow up with the show's host and guest teams. Each reminder tags the contact (short names Cody/Steve/Greg map to full Slack names), includes a copyable sample message (including the show's **Theme** column, if set, for host reminders), and asks the contact to react with :+1: when done. The bot identifies its own prior reminders via Slack message metadata and re-posts daily until a reminder for that (show, kind) receives a :+1: reaction. Shows with a blank contact cell are skipped with a warning log.

**Slack scopes required:** `chat:write`, `chat:write.public`, `users:read`, `users:read.email` (alerts), plus `channels:read`, `channels:history`, and `channels:join` (follow-up reminders). If the history scopes are missing, follow-ups are skipped with an error log and the job still succeeds.

**Testing:** A full suite of `unittest` tests are available to verify models, logic, spreadsheet parsing, and alert/reminder formatting.

## 🚀 Local Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd casting-alerts-bot
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Google Authentication

The bot interacts with Google Sheets and requires valid credentials. It uses Application Default Credentials (ADC). To authenticate locally, run:

```bash
gcloud auth application-default login
```

This generates a JSON credential file that the script will automatically detect.

### 5. Configuration (.env)

Create a `.env` file in the root directory. This is referenced by the Docker scripts and `.gitignore`.

```bash
touch .env
```

**Required Environment Variables:**
* `SLACK_BOT_TOKEN`: A valid Slack Bot OAuth token (starts with `xoxb-`). This is required to lookup users and send messages in the Slack workspace.

## 🛠️ Usage

### Running with Python

**Standard Run:**
```bash
python main.py
```

**Dry Run (No alerts sent):**
Useful for testing without triggering external notifications.
```bash
python main.py --dry-run
```

**Debug Mode:**
Increases log verbosity.
```bash
python main.py --debug
```

**Force Role Alerts:**
Unfilled-role alerts normally only go out on Wednesdays and Saturdays; this flag sends them regardless of the day.
```bash
python main.py --force-role-alerts
```

### Running with Docker

A helper script `build-and-run.sh` is provided to build the image and run the container with the necessary volume mounts for Google Credentials.

```bash
./build-and-run.sh
```
_This script automatically mounts your local gcloud credentials and runs in `--dry-run` mode._

## 🧪 Testing

The project uses Python's built-in `unittest` framework. To run all tests across the project:

```bash
python -m unittest discover -p "test_*.py"
```

## 📂 Project Structure

### Core Modules
* `main.py`: The application entry point. Handles argument parsing, dependency injection, and orchestrates the main workflow.
* `models.py`: Domain data structures (`Show`, `CastingRule`, `CastingAlert`) and alert message formatting logic. No external dependencies.
* `logic.py`: Core business logic for evaluating missed deadlines and grouping alerts by responsible party.
* `spreadsheet.py`: Google Sheets API integration. Handles authentication, fetching raw data, and parsing it into domain models.
* `slack.py`: Slack API integration wrapper. Handles user lookup (by name/email) and message dispatching.

### Infrastructure & Operations
* `build-and-run.sh`: Utility script to build the Docker image and run it locally.
* `Dockerfile`: Defines the Python 3.11-slim environment for the application.
* `cloudbuild.yaml`: Configuration for Google Cloud Build to automate deployment to Cloud Run Jobs.
* `requirements.txt`: Python package dependencies.

## 📝 License

This project is licensed under the MIT License. See the `LICENSE` file for details.