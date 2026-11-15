# pg_dump has to match the server's major version, so the backup image is the server's own image
# plus curl for the upload and the Pushgateway push.
FROM postgres:16-alpine

RUN apk add --no-cache curl

COPY backup.sh /usr/local/bin/backup.sh

USER postgres

ENTRYPOINT ["/bin/sh", "/usr/local/bin/backup.sh"]
