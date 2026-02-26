#!/usr/bin/env bash

docker build -t casting-alerts-bot .
docker run \
	-v ~/.config/gcloud/application_default_credentials.json:/root/.config/gcloud/application_default_credentials.json \
	-e GOOGLE_APPLICATION_CREDENTIALS=/root/.config/gcloud/application_default_credentials.json \
	--env-file .env \
	casting-alerts-bot "$@"
