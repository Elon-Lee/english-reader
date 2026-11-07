"""Remote development must recover lost tunnels and probe real dependencies."""
import contextlib
import io
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import run_remote_dev as dev


class RemoteDevTests(unittest.TestCase):
    def test_tunnel_restarts_and_shutdown_stops_live_child(self):
        handlers, delays, children = {}, [], []
        event = MagicMock()
        event.is_set.side_effect = lambda: event.set.called
        event.wait.side_effect = lambda delay: delays.append(delay)

        def spawn(*_args, **_kwargs):
            child = MagicMock(pid=100 + len(children))
            children.append(child)
            child.poll.return_value = None
            if len(children) == 2:
                def stop_after_reconnect():
                    handlers[signal.SIGTERM](signal.SIGTERM, None)
                    child.poll.return_value = 0
                    return 0
                child.wait.side_effect = stop_after_reconnect
            else:
                child.wait.return_value = 255
                child.poll.return_value = 255
            return child

        with tempfile.TemporaryDirectory() as folder, patch.object(dev, 'STATE', Path(folder)), \
                patch.object(dev.signal, 'signal', side_effect=lambda kind, handler: handlers.update({kind: handler})), \
                patch.object(dev.threading, 'Event', return_value=event), \
                patch.object(dev.subprocess, 'Popen', side_effect=spawn), contextlib.redirect_stdout(io.StringIO()):
            dev.watch_tunnel(['ssh', '-N'])
            self.assertFalse((Path(folder) / 'tunnel.json').exists())
        self.assertEqual(len(children), 2)
        self.assertEqual(delays, [1])
        children[1].terminate.assert_called_once()

    def test_real_dependency_probe_rejects_closed_remote_provider(self):
        environment = {'DATABASE_URL': 'postgresql://localhost/test', 'REDIS_URL': 'redis://localhost/0', 'SHIYUE_CAPTCHA_SECRET': 'test-secret'}
        connection = MagicMock()
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        cache = MagicMock()
        cache.ping.return_value = True
        with patch('psycopg.connect', return_value=connection), patch('redis.Redis.from_url', return_value=cache), \
                patch.object(dev, 'urlopen', side_effect=ConnectionRefusedError), self.assertRaises(ConnectionRefusedError):
            dev.assert_dependencies(environment)
        cache.close.assert_called_once()

    def test_real_dependency_probe_requires_valid_rotation_image(self):
        environment = {'DATABASE_URL': 'postgresql://localhost/test', 'REDIS_URL': 'redis://localhost/0', 'SHIYUE_CAPTCHA_SECRET': 'test-secret'}
        connection = MagicMock()
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(json.dumps({'code': 503}).encode())
        with patch('psycopg.connect', return_value=connection), patch('redis.Redis.from_url'), \
                patch.object(dev, 'urlopen', return_value=response), self.assertRaisesRegex(RuntimeError, 'ROTATE'):
            dev.assert_dependencies(environment)


if __name__ == '__main__':
    unittest.main()
