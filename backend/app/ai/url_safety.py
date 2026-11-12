"""Adresses d'IA choisies par une famille (Ollama, « autre service ») : le serveur les appelle lui-
même, elles ne doivent pas le faire parler à ce qui est derrière lui (SSRF, §5.70).

Toujours refusées :
- les services internes de Ludifun (`db`, `recherche`, `api`, conteneur PostgreSQL) ;
- les adresses de métadonnées des hébergeurs (169.254.0.0/16, fe80::/10, `metadata…`) : elles
  donnent les secrets d'un serveur loué ;
- une adresse avec identifiants (`http://nom:mot@…`), l'adresse « 0.0.0.0 » et les adresses
  réservées ou de diffusion.

En production (serveur partagé entre familles, adresses libres permises par
LUDIFUN_ALLOW_CUSTOM_AI_URL), aussi : la machine elle-même (localhost, 127.x, ::1) et le réseau
local (10.x, 172.16-31.x, 192.168.x, fc00::/7), sauf l'Ollama réglé par le serveur. Sur le PC de
la famille (hors production), Ollama sur ce PC ou sur un autre ordinateur de la maison reste
possible : c'est l'usage prévu.

Limite : un nom de domaine n'est pas résolu ici ; s'il pointait vers une adresse interne, il ne
serait pas refusé.
"""

import ipaddress
from urllib.parse import urlsplit

INTERNAL_HOSTS = frozenset({"db", "recherche", "api", "postgres", "ludifun-db-1", "ludifun-api-1"})
METADATA_HOSTS = frozenset({"metadata", "metadata.google.internal", "instance-data"})
LOCAL_NAMES = frozenset({"localhost", "host.docker.internal"})


def _ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def refused_ai_url(url: str, *, strict: bool, allowed: frozenset[str] = frozenset()) -> str | None:
    """La raison du refus (pour le parent), ou None si l'adresse peut être appelée.

    `strict` : serveur de production ; `allowed` : hôtes réglés par le serveur lui-même (son
    Ollama), toujours permis."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme not in ("http", "https") or not host:
        return "Adresse invalide : elle doit commencer par http:// ou https://."
    if parts.username or parts.password:
        return "L'adresse ne doit pas contenir d'identifiant ni de mot de passe : mettez la clé à part."
    if host in allowed:
        return None
    if host in INTERNAL_HOSTS:
        return "Cette adresse est un service interne de Ludifun, pas une IA."
    ip = _ip(host)
    if host in METADATA_HOSTS or (ip is not None and ip.is_link_local):
        return "Cette adresse est réservée à l'hébergeur du serveur."
    # « ::1 » est aussi « réservée » pour Python : c'est la machine elle-même, jugée plus bas.
    if ip is not None and (ip.is_unspecified or ip.is_multicast or (ip.is_reserved and not ip.is_loopback)):
        return "Cette adresse n'est pas celle d'un service d'IA."
    if strict and (host in LOCAL_NAMES or (ip is not None and (ip.is_loopback or ip.is_private))):
        return "Ce serveur n'autorise pas une IA sur son réseau local : utilisez une adresse publique."
    return None
