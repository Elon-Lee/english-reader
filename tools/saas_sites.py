"""Site capabilities come from authenticated local gateways, never the browser."""
from contextlib import contextmanager
from contextvars import ContextVar
import hmac
import ipaddress
import os
from urllib.parse import unquote, urlsplit

from saas_auth import SaaSError, SaaSConfigurationError


_SITE = ContextVar('shiyue_site', default='cn')
_SITES = {'cn', 'intl'}
_COMMERCIAL_PREFIXES = (
    '/api/membership', '/api/commerce', '/api/billing', '/api/payments',
    '/api/admin/commerce', '/api/admin/payment-config', '/api/admin/payment-orders',
    '/api/admin/plan-versions', '/api/admin/manual-orders', '/api/admin/subscriptions',
    '/api/member-invites', '/api/public/stats', '/pricing', '/purchase', '/refunds',
)


def current_site():
    return _SITE.get()


@contextmanager
def site_context(site):
    if site not in _SITES:
        raise ValueError('Unknown site')
    token = _SITE.set(site)
    try:
        yield site
    finally:
        _SITE.reset(token)


def is_commercial_path(path):
    path = unquote(urlsplit(path).path)
    return any(path == prefix or path.startswith(prefix + '/') for prefix in _COMMERCIAL_PREFIXES)


def _origin(value, environment):
    try:
        if not value or any(character.isspace() or ord(character) < 33 for character in value):
            raise ValueError()
        parts = urlsplit(value.rstrip('/'))
        parts.port
        if (parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username
                or parts.password or parts.path or parts.query or parts.fragment):
            raise ValueError()
        if parts.scheme != 'https' and environment.get('SHIYUE_DEPLOYMENT_MODE', 'local') != 'local':
            raise ValueError()
        return parts.geturl()
    except (ValueError, TypeError):
        raise SaaSConfigurationError('站点基础地址必须是可信的完整 HTTPS 域名。') from None


def app_base_url(environment=None):
    environment = os.environ if environment is None else environment
    key = 'INTL_APP_BASE_URL' if current_site() == 'intl' else 'CN_APP_BASE_URL'
    value = environment.get(key, '').strip()
    if current_site() == 'cn':
        value = value or environment.get('APP_BASE_URL', '').strip() or 'http://localhost:8765'
    return _origin(value, environment)


def _one_header(headers, name):
    if hasattr(headers, 'get_all'):
        values = headers.get_all(name, [])
        if len(values) > 1:
            raise SaaSError('invalid_site', '站点入口验证失败。', 403)
        return values[0] if values else ''
    return next((value for key, value in headers.items() if key.lower() == name.lower()), '')


def request_site(headers, peer, environment=None):
    environment = os.environ if environment is None else environment
    claimed = _one_header(headers, 'X-Shiyue-Site')
    configured = any(environment.get(key, '') for key in ('CN_GATEWAY_TOKEN', 'INTL_GATEWAY_TOKEN'))
    if not configured:
        # Existing single-site/local clients remain domestic. A header can never
        # enable commerce until a corresponding gateway secret is configured.
        if claimed not in {'', 'cn'}:
            raise SaaSError('invalid_site', '站点入口验证失败。', 403)
        return 'cn'
    try:
        loopback = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        loopback = False
    expected = environment.get('INTL_GATEWAY_TOKEN' if claimed == 'intl' else 'CN_GATEWAY_TOKEN', '')
    supplied = _one_header(headers, 'X-Shiyue-Site-Token')
    if (not loopback or claimed not in _SITES or not expected or not supplied
            or not hmac.compare_digest(str(supplied), str(expected))):
        raise SaaSError('invalid_site', '站点入口验证失败。', 403)
    raw_host = _one_header(headers, 'X-Shiyue-Original-Host')
    try:
        if not raw_host or any(character.isspace() or ord(character) < 33 or ord(character) == 127 for character in raw_host):
            raise ValueError()
        host = urlsplit('//' + raw_host)
        host.port
        if host.username or host.password or host.path or host.query or host.fragment:
            raise ValueError()
        with site_context(claimed):
            origin = urlsplit(app_base_url(environment))
        if host.hostname != origin.hostname or host.port not in {None, origin.port or (443 if origin.scheme == 'https' else 80)}:
            raise ValueError()
    except ValueError:
        raise SaaSError('invalid_site', '站点入口验证失败。', 403) from None
    return claimed
