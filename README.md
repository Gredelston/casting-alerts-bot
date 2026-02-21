# Casting Alerts Bot

A Python automation for Improv Boulder that monitors casting spreadsheets and alerts show production teams when show roles are unassigned.

## 📋 Prerequisites

* **Python 3.11+**
* **Docker** (optional, for containerized execution)
* **Google Cloud SDK** (`gcloud`) (Required for authentication)

## 🚀 Local Setup

### 1.  Clone the repository

```bash
git clone <repository-url>
cd casting-alerts-bot
```

### 2.  Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

### 3.  Install dependencies

```bash
pip install -r requirements.txt
```

_Dependencies include `google-api-python-client`, `google-auth`, and `slack-sdk`._

### 4.  Google Authentication

The bot interacts with Google Sheets and requires valid credentials. It uses Application Default Credentials (ADC).

To authenticate locally, run:

```bash
gcloud auth application-default login
```

This generates a JSON credential file (usually in `~/.config/gcloud/application_default_credentials.json`) that the script will automatically detect.

### 5.  Configuration (.env)

Create a `.env` file in the root directory. This is referenced by the Docker scripts and `.gitignore`.

```bash
touch .env
```

## 🛠️ Usage

### Running with Python

You can run the script directly with Python.

**Standard Run:**

```bash
python main.py
```

**Dry Run (No alerts sent):**

Useful for testing without triggering external notifications (e.g., Slack).

```bash
python main.py --dry-run
```

### Running with Docker

A helper script `build-and-run.sh` is provided to build the image and run the container with the necessary volume mounts for Google Credentials.

```bash
./build-and-run.sh
```

_This script automatically mounts your local gcloud credentials and runs in `--dry-run` mode._

## 📂 Project Structure

*   `main.py`: The application entry point. Handles argument parsing, Google Sheets connection, and show data parsing.
*   `build-and-run.sh`: Utility script to build the Docker image and run it with local credentials mounted.
*   `Dockerfile`: Defines the Python 3.11-slim environment for the application.
*   `cloudbuild.yaml`: Configuration for Google Cloud Build to automate deployment to Cloud Run Jobs.

## 📝 License

This project is licensed under the MIT License. See the `LICENSE` file for details.
