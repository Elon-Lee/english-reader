import ast
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, unquote, urlsplit

from saas_auth import SaaSError, SaaSConfigurationError
from saas_media_analytics import period_range
import saas_server_metrics as metrics


class AnalyticsRangeTests(unittest.TestCase):
    def test_defaults_and_leap_year(self):
        today = date(2024, 2, 29)
        for period, count in [('day', 30), ('month', 12), ('year', 5)]:
            start, end, buckets = period_range(period, today=today)
            self.assertEqual(end, today)
            self.assertEqual(len(buckets), count)
        self.assertEqual(period_range('day', '2024-02-28', '2024-02-29', today)[2], ['2024-02-28', '2024-02-29'])

    def test_invalid_and_unbounded_ranges_are_rejected(self):
        for args in [('week', '', ''), ('day', 'bad', ''), ('day', '2024-02-30', ''),
                     ('day', '2025-01-01', '2024-01-01'), ('day', '2020-01-01', '2026-01-01'),
                     ('month', '2000-01-01', ''), ('year', '1970-01-01', ''), ('day', '', '9999-12-31')]:
            with self.subTest(args=args), self.assertRaises(SaaSError): period_range(*args)


class MetricsTests(unittest.TestCase):
    def setUp(self):
        metrics.CACHE = None; metrics.LAST_SAMPLE = 0; metrics.LAST_NETWORK = None; metrics.LAST_ROOT = None; metrics.HISTORY.clear()

    def test_real_snapshot_cached_and_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            first = metrics.server_metrics(root)
            self.assertTrue(first['sampledAt'])
            self.assertGreater(first['memory']['total'], 0)
            self.assertGreater(first['disks'][0]['total'], 0)
            self.assertTrue(0 <= first['cpu']['percent'] <= 100)
            self.assertIsNone(first['network']['receivePerSecond'])
            self.assertIs(first, metrics.server_metrics(root))
            self.assertEqual(len(first['history']), 1)
            metrics.HISTORY.extend([first['history'][0]] * 150)
            self.assertEqual(len(metrics.HISTORY), 120)

    def test_missing_dependency_is_controlled(self):
        with patch.dict('sys.modules', {'psutil': None}), self.assertRaises(SaaSError) as error:
            metrics.server_metrics('/tmp')
        self.assertEqual(error.exception.status, 503)

    def test_cgroup_limits_and_unlimited(self):
        files = {'/sys/fs/cgroup/memory.max': '1000', '/sys/fs/cgroup/memory.current': '350', '/sys/fs/cgroup/cpu.max': '150000 100000'}
        with patch.object(metrics, '_read', side_effect=files.get):
            result = metrics.container_limits()
        self.assertEqual(result['memory']['percent'], 35)
        self.assertEqual(result['cpuLimit'], 1.5)
        with patch.object(metrics, '_read', return_value='max'):
            self.assertEqual(metrics.container_limits(), {})

    def test_partial_failure_is_not_reported_as_zero(self):
        import psutil
        with patch.object(psutil, 'virtual_memory', side_effect=OSError('not available')):
            result = metrics.server_metrics('/tmp')
        self.assertIsNone(result['memory'])
        self.assertIsNone(result['history'][-1]['memory'])
        self.assertIn('内存', result['errors'])


class AdminRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path(__file__).with_name('reader_server.py').read_text())
        handler = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Handler')
        methods = [node for node in handler.body if isinstance(node, ast.FunctionDef) and node.name in ('admin_get', 'admin_required')]
        node = ast.ClassDef(name='TestHandler', bases=[], keywords=[], body=methods, decorator_list=[])
        ast.fix_missing_locations(node)
        cls.namespace = dict(SaaSError=SaaSError, SaaSConfigurationError=SaaSConfigurationError,
                             parse_qs=parse_qs, SAAS=Mock(), MEDIA=SimpleNamespace(media_root=Path('/tmp')),
                             unquote=unquote)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<admin-routes>', 'exec'), cls.namespace)

    def test_admin_only_both_shared_endpoints(self):
        for path in ('/api/admin/media-assets/statistics?period=month', '/api/admin/server-metrics'):
            for admin in (False, True):
                with self.subTest(path=path, admin=admin):
                    handler = self.namespace['TestHandler']()
                    handler._saas_session = {'id': 'fixture', 'is_admin': admin}; handler.reply = Mock()
                    with patch('saas_media_analytics.media_statistics', return_value={'ok': True}) as stats, patch.object(metrics, 'server_metrics', return_value={'ok': True}) as sampler:
                        handler.admin_get(urlsplit(path))
                    if admin:
                        handler.reply.assert_called_once_with({'ok': True})
                        self.assertEqual(stats.call_count + sampler.call_count, 1)
                    else:
                        self.assertEqual(handler.reply.call_args.args[1], 403)
                        self.assertEqual(stats.call_count + sampler.call_count, 0)


if __name__ == '__main__': unittest.main()
