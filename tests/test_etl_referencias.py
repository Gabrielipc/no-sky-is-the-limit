"""Cloud jobs that mirror and measure the reference sites (scripts/etl_referencias.py)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from pipelines import etl_mirror as mirror
from scripts import etl_referencias as job


class ReferenceJobsTest(unittest.TestCase):
    def test_each_body_only_mirrors_its_own_products(self) -> None:
        manifest = mirror.load_manifest()
        moon, mars = job.body_ids(manifest, 'Moon', [1]), job.body_ids(manifest, 'Mars', [1])
        self.assertTrue(moon and mars)
        self.assertFalse(set(moon) & set(mars))  # what lets the two jobs run on two clouds at once
        self.assertNotIn('mola-dem-463m', mars)  # tier 2 is optional context
        self.assertIn('mola-dem-463m', job.body_ids(manifest, 'Mars', [1, 2]))

    def run_job(self, argv: list[str], returncode: int = 0):
        checked = [{'id': 'x', 'ok': True, 'sha256': 'ab'}]
        with mock.patch.object(job, 'run_mirror', return_value=checked) as run_mirror, \
                mock.patch.object(job.subprocess, 'run', return_value=mock.Mock(returncode=returncode)) as sub, \
                mock.patch('sys.argv', ['etl_referencias.py', *argv]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = job.main()
        return code, run_mirror, sub

    def test_luna_mirrors_the_moon_then_measures(self) -> None:
        code, run_mirror, sub = self.run_job(['luna', '--workers', '3'])
        run_mirror.assert_called_once_with('Moon', [1], 3)
        self.assertEqual(sub.call_args.args[0][-2:], [str(job.ROOT / 'scripts/etl_luna.py'), 'referencia'][-2:])
        self.assertEqual(code, 0)

    def test_a_failed_measurement_fails_the_job(self) -> None:
        code, _, _ = self.run_job(['luna'], returncode=2)
        self.assertEqual(code, 2)

    def test_skip_measure_only_mirrors(self) -> None:
        code, _, sub = self.run_job(['luna', '--skip-measure'])
        sub.assert_not_called()
        self.assertEqual(code, 0)

    def test_marte_mirrors_mars_and_does_not_pretend_to_measure(self) -> None:
        code, run_mirror, sub = self.run_job(['marte'])
        run_mirror.assert_called_once_with('Mars', [1], 4)
        sub.assert_not_called()
        self.assertEqual(code, 0)

    def test_a_failed_mirror_stops_the_job_before_measuring(self) -> None:
        with mock.patch.object(job, 'run_mirror', side_effect=SystemExit('1 productos con error')), \
                mock.patch.object(job.subprocess, 'run') as sub, mock.patch('sys.argv', ['x', 'luna']):
            with self.assertRaises(SystemExit):
                job.main()
        sub.assert_not_called()


if __name__ == '__main__':
    unittest.main()
