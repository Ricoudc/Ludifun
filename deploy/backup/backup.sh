#!/bin/sh
# Une sauvegarde chiffrée par jour dans /backups ; les plus anciennes que BACKUP_KEEP_DAYS sont effacées.
# Restauration (sur un poste qui a la clé privée) :
#   age -d -i cle-ludifun.txt ludifun-AAAAMMJJ.dump.age | pg_restore --clean --if-exists -d ludifun
set -eu
stamp=$(date -u +%Y%m%d-%H%M)
target="/backups/ludifun-$stamp.dump.age"
pg_dump --format=custom | age -r "$BACKUP_AGE_RECIPIENT" > "$target.part"
mv "$target.part" "$target"
find /backups -name 'ludifun-*.dump.age' -mtime +"${BACKUP_KEEP_DAYS:-30}" -delete
echo "Sauvegarde écrite : $(basename "$target") ($(du -h "$target" | cut -f1))"
