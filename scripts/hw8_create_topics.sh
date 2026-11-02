#!/usr/bin/env bash
set -euo pipefail

PREFIX="${PREFIX:-s8360}"
BOOTSTRAP="${BOOTSTRAP:-localhost:9092}"
KT="${KAFKA_TOPICS:-/opt/kafka/bin/kafka-topics.sh}"

create() {
  "$KT" --create --if-not-exists --topic "${PREFIX}_$1" --partitions "$2" --replication-factor 1 --bootstrap-server "$BOOTSTRAP"
}

create entity_requests 1
create entity_responses 1
create inbox 1
create tasks 2
create drafts 1
create final 1
create dead_letter 1
"$KT" --list --bootstrap-server "$BOOTSTRAP"
