# Sauvegarde nocturne : pg_dump chiffré pour une clé publique age (la clé privée reste hors du serveur).
FROM postgres:16-alpine
RUN apk add --no-cache age
COPY backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh
CMD ["sh", "-c", "while true; do /usr/local/bin/backup.sh; sleep 86400; done"]
