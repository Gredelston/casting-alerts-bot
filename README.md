# casting-alerts-bot
A Python automation for Improv Boulder that monitors casting spreadsheets and alerts show production teams when show roles are unassigned.

# Build & Run

To build the Docker container:

```
docker build -t casting-alerts-bot
```

To run the container:

```
docker run --env-file .env casting-alerts-bot
```
