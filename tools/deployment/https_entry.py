"""Generate the independent Docker HTTPS edge; execution belongs to the caller.

Only the small, nonsecret rediscovery manifest lives inside the application root.
Certificates, ACME accounts, configuration, locks and renewal units survive app
reinstallation. Generated scripts require root, Docker, ss, flock and systemd.
"""
import hashlib
import ipaddress
import json
import re
import shlex


NGINX_IMAGE = 'nginx:1.28-alpine'
CERTBOT_IMAGE = 'certbot/certbot:v5.4.0'
CONTAINER = 'shiyue-https'
OWNER_LABEL = 'io.shiyue.https.remote-root'


def normalize_domain(value):
    """Return an ASCII DNS name, or the empty optional-domain value."""
    if value is None or value == '':
        return ''
    if not isinstance(value, str) or any(c.isspace() for c in value):
        raise ValueError('public_domain must be a DNS name without whitespace')
    try:
        domain = value.encode('idna').decode('ascii').lower()
    except UnicodeError as exc:
        raise ValueError('public_domain is not a valid DNS name') from exc
    labels = domain.split('.')
    if (len(domain) > 253 or len(labels) < 2 or labels[-1].isdigit()
            or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                   for label in labels)):
        raise ValueError('public_domain must contain valid DNS labels')
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        return domain
    raise ValueError('public_domain must be a domain, not an IP address')


def frontend_url(target):
    domain = normalize_domain(target.get('public_domain'))
    if domain:
        return 'https://' + domain
    scheme = 'https' if target.get('use_https', True) else 'http'
    host = str(target['host'])
    if ':' in host and not host.startswith('['):
        host = '[' + host + ']'
    return f'{scheme}://{host}:5173'


def _remote_root(target):
    root = target.get('remote_root', '')
    if (not isinstance(root, str) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', root)
            or any(part in ('.', '..', '') for part in root[1:].rstrip('/').split('/'))):
        raise ValueError('remote_root must be a safe absolute application directory')
    return root.rstrip('/')


def entry_paths(target):
    root = _remote_root(target)
    suffix = hashlib.sha256(root.encode('utf-8')).hexdigest()[:12]
    state = '/var/lib/shiyue/https/' + suffix
    return {
        'state_root': state,
        'nginx_dir': state + '/nginx',
        'nginx_config': state + '/nginx/default.conf',
        'letsencrypt': state + '/letsencrypt',
        'webroot': state + '/webroot',
        'work': state + '/work',
        'logs': state + '/logs',
        'renew_script': state + '/renew.sh',
        'lock': state + '/entry.lock',
        'manifest': root + '/shared/config/https-entry.json',
        'service_name': 'shiyue-https-renew-' + suffix + '.service',
        'timer_name': 'shiyue-https-renew-' + suffix + '.timer',
    }


def _http_config(domain):
    return '''server {
    listen 80 default_server;
    server_name @DOMAIN@;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/acme;
        try_files $uri =404;
    }
    location / { return 308 https://@DOMAIN@$request_uri; }
}
'''.replace('@DOMAIN@', domain)


def _https_config(domain):
    return _http_config(domain) + '''
server {
    listen 443 ssl default_server;
    server_name @DOMAIN@;
    ssl_certificate /etc/letsencrypt/live/@DOMAIN@/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/@DOMAIN@/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SHIYUE_TLS:10m;
    ssl_session_timeout 1d;
    client_max_body_size 20g;
    client_body_timeout 600s;
    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Connection "";
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_connect_timeout 30s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }
}
'''.replace('@DOMAIN@', domain)


def _render(template, values):
    for key, value in values.items():
        template = template.replace('@' + key + '@', value)
    return template


def _renew_script(values):
    return _render(r'''#!/bin/bash
set -euo pipefail
umask 022
state=@STATE@
remote_root=@ROOT@
domain=@DOMAIN@
container=@CONTAINER@
certbot_image=@CERTBOT_IMAGE@
for arg in "$@"; do
    case "$arg" in --dry-run|--run-deploy-hooks) ;; *) echo "Unsupported renewal argument" >&2; exit 2 ;; esac
done
exec 9>"$state/entry.lock"
flock -x 9
owner=$(docker inspect --format '{{index .Config.Labels "@OWNER_LABEL@"}}' "$container")
[ "$owner" = "$remote_root" ] || { echo "HTTPS container ownership conflict" >&2; exit 1; }
# A failed ACME attempt or nginx validation never consumes the reload marker.
docker run --rm --network host \
    -v "$state/letsencrypt:/etc/letsencrypt:z" \
    -v "$state/webroot:/var/www/acme:z" \
    -v "$state/work:/var/lib/letsencrypt:z" \
    -v "$state/logs:/var/log/letsencrypt:z" \
    "$certbot_image" renew --cert-name "$domain" --non-interactive --no-random-sleep-on-renew \
    --webroot --webroot-path /var/www/acme \
    --deploy-hook 'touch /var/lib/letsencrypt/reload-required' "$@"
if [ -f "$state/work/reload-required" ]; then
    docker exec "$container" nginx -t
    docker exec "$container" nginx -s reload
    rm -f "$state/work/reload-required"
fi
''', values)


def install_script(target):
    """Return an idempotent installation script without contacting the host."""
    root = _remote_root(target)
    domain = normalize_domain(target.get('public_domain'))
    if not domain:
        raise ValueError('public_domain is required to install the HTTPS entry')
    paths = entry_paths(target)
    email = target.get('acme_email') or ''
    if email and (not isinstance(email, str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)):
        raise ValueError('acme_email must be a valid email without whitespace')
    email_args = '--email ' + shlex.quote(email) if email else '--register-unsafely-without-email'
    values = {
        'STATE': shlex.quote(paths['state_root']),
        'ROOT': shlex.quote(root),
        'DOMAIN': shlex.quote(domain),
        'CONTAINER': shlex.quote(CONTAINER),
        'NGINX_IMAGE': shlex.quote(NGINX_IMAGE),
        'CERTBOT_IMAGE': shlex.quote(CERTBOT_IMAGE),
        'OWNER_LABEL': OWNER_LABEL,
        'MANIFEST': shlex.quote(paths['manifest']),
        'SERVICE_NAME': paths['service_name'],
        'TIMER_NAME': paths['timer_name'],
        'EMAIL_ARGS': email_args,
        'HTTP_CONFIG': _http_config(domain),
        'HTTPS_CONFIG': _https_config(domain),
    }
    values['RENEW_SCRIPT'] = _renew_script(values)
    manifest = {'version': 1, 'public_domain': domain, 'remote_root': root,
                'frontend_url': frontend_url(target), 'container': CONTAINER, **paths}
    values['MANIFEST_JSON'] = json.dumps(manifest, sort_keys=True)
    values['READY'] = shlex.quote('SHIYUE_HTTPS_ENTRY_READY ' + json.dumps(manifest, sort_keys=True))
    return _render(r'''#!/bin/bash
set -euo pipefail
umask 022
state=@STATE@
remote_root=@ROOT@
domain=@DOMAIN@
container=@CONTAINER@
nginx_image=@NGINX_IMAGE@
certbot_image=@CERTBOT_IMAGE@
manifest=@MANIFEST@
command -v docker >/dev/null
command -v ss >/dev/null
command -v flock >/dev/null
command -v systemctl >/dev/null
mkdir -p "$state"
exec 9>"$state/entry.lock"
flock -x 9
exists=false
if docker inspect "$container" >/dev/null 2>&1; then
    exists=true
    owner=$(docker inspect --format '{{index .Config.Labels "@OWNER_LABEL@"}}' "$container")
    [ "$owner" = "$remote_root" ] || { echo "HTTPS container ownership conflict" >&2; exit 1; }
fi
container_running() {
    [ "$exists" = true ] && [ "$(docker inspect --format '{{.State.Running}}' "$container")" = true ]
}
# Never stop a listener to obtain 80/443, including an unrelated Docker container.
if ! container_running; then
    listeners=$(ss -H -ltn '( sport = :80 or sport = :443 )')
    [ -z "$listeners" ] || { echo "Port 80 or 443 is already in use" >&2; exit 1; }
fi
ensure_image() {
    image=$1
    mirror=$2
    if docker image inspect "$image" >/dev/null 2>&1; then return 0; fi
    # Use the project's existing mirror without changing Docker daemon settings.
    if docker pull "$mirror"; then
        docker tag "$mirror" "$image"
    else
        docker pull "$image"
    fi
}
ensure_image "$nginx_image" m.daocloud.io/docker.io/library/nginx:1.28-alpine
ensure_image "$certbot_image" m.daocloud.io/docker.io/certbot/certbot:v5.4.0
mkdir -p "$state/nginx" "$state/letsencrypt" "$state/webroot/.well-known/acme-challenge" \
    "$state/work" "$state/logs" "$state/backups"
chmod 700 "$state/letsencrypt" "$state/work" "$state/logs" "$state/backups"
chmod 755 "$state" "$state/nginx" "$state/webroot" "$state/webroot/.well-known" \
    "$state/webroot/.well-known/acme-challenge"
config="$state/nginx/default.conf"
backup=''
rollback_needed=false
had_config=false
restore_config() {
    if [ "$had_config" = true ]; then
        cp -p "$backup" "$config.restore"
        mv -f "$config.restore" "$config"
    else
        rm -f "$config"
    fi
    rollback_needed=false
}
cleanup() {
    result=$?
    if [ "$rollback_needed" = true ]; then restore_config; fi
    rm -f "$state/nginx/candidate.tmp"
    exit "$result"
}
trap cleanup EXIT
validate_nginx() {
    docker run --rm --network host \
        -v "$state/nginx:/etc/nginx/conf.d:ro,z" \
        -v "$state/letsencrypt:/etc/letsencrypt:ro,z" \
        -v "$state/webroot:/var/www/acme:ro,z" "$nginx_image" nginx -t
}
apply_config() {
    had_config=false
    if [ -f "$config" ]; then
        had_config=true
        backup=$(mktemp "$state/backups/nginx.XXXXXXXX")
        cp -p "$config" "$backup"
    fi
    rollback_needed=true
    mv -f "$state/nginx/candidate.tmp" "$config"
    if ! validate_nginx; then
        restore_config
        echo "HTTPS configuration rejected; previous configuration restored" >&2
        return 1
    fi
    if container_running; then
        if ! docker exec "$container" nginx -t || ! docker exec "$container" nginx -s reload; then
            restore_config
            docker exec "$container" nginx -t && docker exec "$container" nginx -s reload || true
            echo "HTTPS reload failed; previous configuration restored" >&2
            return 1
        fi
    fi
    rollback_needed=false
}
if ! container_running; then
    if [ ! -f "$config" ]; then
        cat > "$state/nginx/candidate.tmp" <<'SHIYUE_HTTP_CONFIG'
@HTTP_CONFIG@
SHIYUE_HTTP_CONFIG
        apply_config
    else
        validate_nginx
    fi
    if [ "$exists" = true ]; then
        docker start "$container" >/dev/null
    else
        docker run -d --name "$container" --restart unless-stopped --network host \
            --label "@OWNER_LABEL@=$remote_root" \
            -v "$state/nginx:/etc/nginx/conf.d:ro,z" \
            -v "$state/letsencrypt:/etc/letsencrypt:ro,z" \
            -v "$state/webroot:/var/www/acme:ro,z" "$nginx_image" >/dev/null
        exists=true
    fi
fi
# Existing TLS configuration remains active while certbot obtains/reuses a cert.
if ! docker run --rm --network host \
    -v "$state/letsencrypt:/etc/letsencrypt:z" \
    -v "$state/webroot:/var/www/acme:z" \
    -v "$state/work:/var/lib/letsencrypt:z" \
    -v "$state/logs:/var/log/letsencrypt:z" \
    "$certbot_image" certonly --webroot --webroot-path /var/www/acme \
    --cert-name "$domain" --domain "$domain" --keep-until-expiring \
    --server https://acme-v02.api.letsencrypt.org/directory \
    --non-interactive --agree-tos @EMAIL_ARGS@; then
    echo "SHIYUE_HTTPS_CERTIFICATE_FAILED: Let's Encrypt domain validation failed; check public DNS, port 80 and provider domain restrictions. Application services remain running." >&2
    exit 10
fi
test -s "$state/letsencrypt/live/$domain/fullchain.pem"
test -s "$state/letsencrypt/live/$domain/privkey.pem"
cat > "$state/nginx/candidate.tmp" <<'SHIYUE_HTTPS_CONFIG'
@HTTPS_CONFIG@
SHIYUE_HTTPS_CONFIG
apply_config
cat > "$state/renew.sh.tmp" <<'SHIYUE_RENEW_SCRIPT'
@RENEW_SCRIPT@
SHIYUE_RENEW_SCRIPT
chmod 700 "$state/renew.sh.tmp"
mv -f "$state/renew.sh.tmp" "$state/renew.sh"
mkdir -p /etc/systemd/system
cat > "/etc/systemd/system/@SERVICE_NAME@.tmp" <<SHIYUE_RENEW_SERVICE
[Unit]
Description=Shiyue HTTPS certificate renewal
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
TimeoutStartSec=3600
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/bin/bash $state/renew.sh
SHIYUE_RENEW_SERVICE
mv -f "/etc/systemd/system/@SERVICE_NAME@.tmp" "/etc/systemd/system/@SERVICE_NAME@"
cat > "/etc/systemd/system/@TIMER_NAME@.tmp" <<'SHIYUE_RENEW_TIMER'
[Unit]
Description=Renew Shiyue HTTPS certificates twice daily

[Timer]
OnCalendar=*-*-* 03,15:00:00
Persistent=true
Unit=@SERVICE_NAME@

[Install]
WantedBy=timers.target
SHIYUE_RENEW_TIMER
mv -f "/etc/systemd/system/@TIMER_NAME@.tmp" "/etc/systemd/system/@TIMER_NAME@"
systemctl daemon-reload
systemctl enable --now "@TIMER_NAME@"
mkdir -p "$(dirname "$manifest")"
cat > "$manifest.tmp" <<'SHIYUE_ENTRY_MANIFEST'
@MANIFEST_JSON@
SHIYUE_ENTRY_MANIFEST
chmod 644 "$manifest.tmp"
mv -f "$manifest.tmp" "$manifest"
printf '%s\n' @READY@
''', values)
