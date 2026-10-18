# Backup image (P7.4, ADR 0024): the Postgres 16 client tools (and a server, for the scratch
# restore check) from the official image, plus age, bash and a bare python3 for the retention
# and scheduling logic in trainsync.ops (standard library only). Build context: the repo root.
FROM postgres:16.15-alpine3.24

RUN apk add --no-cache age~1 bash~5 python3~3 \
    && install -d -o postgres -g postgres -m 0750 /backups

COPY src/trainsync/__init__.py /opt/backup/trainsync/__init__.py
COPY src/trainsync/ops/ /opt/backup/trainsync/ops/
COPY --chmod=0755 deploy/backup/backup.sh /opt/backup/backup.sh
COPY deploy/backup/counts.sql /opt/backup/counts.sql

ENV PYTHONPATH=/opt/backup \
    PYTHONDONTWRITEBYTECODE=1 \
    BACKUP_DIR=/backups
USER postgres
WORKDIR /tmp
ENTRYPOINT ["/opt/backup/backup.sh"]
CMD ["loop"]
