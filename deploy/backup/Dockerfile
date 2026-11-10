# Scheduled backups for JobPilot: pg_dump + uploads archive, optional encryption and off-host copy.
FROM postgres:16-alpine
RUN apk add --no-cache openssl tzdata
COPY backup.sh loop.sh /backup/
RUN chmod +x /backup/*.sh
ENTRYPOINT ["/backup/loop.sh"]
