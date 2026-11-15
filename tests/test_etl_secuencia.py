"""The cloud orchestrator runs what it can and skips steps that need the world sweep."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts import etl_secuencia as seq


class SequenceTest(unittest.TestCase):
    def run_seq(self, store: Path, steps: str, fail: set[str] = frozenset()) -> tuple[dict, list[list[str]]]:
        calls = []

        def runner(cmd, cwd=None):
            calls.append(cmd)
            name = Path(cmd[1]).name + (':' + cmd[2] if cmd[1].endswith('etl_capa_global.py') else '')
            return subprocess.CompletedProcess(cmd, 1 if name in fail else 0)

        args = seq.main.__globals__['argparse'].Namespace(
            steps=steps, store_dir=store, layer=['snow'], workers=4, ati_tiles=3, ati_per_tile=2,
            release_version='r1', similarity_model=None, summary=str(store.parent / 'secuencia.json'), strict=False,
            model=store.parent / 'model.joblib', memory_limit='1GB', set_current=True)
        return seq.run(args, runner=runner), calls

    def test_without_sweep_only_build_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary, calls = self.run_seq(Path(tmp) / 'store', 'build,sample,ati-cluster,publish')
            self.assertEqual(summary['steps']['build']['status'], 'ok')
            for step in ('sample', 'ati-cluster', 'publish'):
                self.assertEqual(summary['steps'][step]['status'], 'skipped')
            self.assertEqual(len(calls), 1)
            self.assertIn('--layer', calls[0])
            written = json.loads((Path(tmp) / 'secuencia.json').read_text())
            self.assertEqual(written['steps']['sample']['status'], 'skipped')

    def test_luna_step_runs_without_earth_base_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary, calls = self.run_seq(Path(tmp) / 'store', 'luna')
            self.assertEqual(summary['steps']['luna']['status'], 'ok')
            self.assertEqual(len(calls), 1)
            self.assertEqual(Path(calls[0][1]).name, 'etl_luna.py')
            self.assertEqual(calls[0][-1], 'referencia')
            self.assertIn('--store-dir', calls[0])

    def test_with_sweep_runs_everything_and_continues_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / 'store'
            (store / 'base' / 'utm_zone_band=N01').mkdir(parents=True)
            (store / 'base' / 'utm_zone_band=N01' / 'part.parquet').write_bytes(b'')
            summary, calls = self.run_seq(store, 'build,sample,ati-cluster', fail={'etl_capa_global.py:build'})
            self.assertEqual([s['status'] for s in summary['steps'].values()], ['failed', 'ok', 'ok'])
            ati = calls[2]
            self.assertIn('--no-topographic-candidates', ati)
            self.assertEqual(ati[ati.index('--background-cluster-tiles') + 1], '3')

    def test_fit_then_publish_packages_the_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / 'store'
            (store / 'base').mkdir(parents=True)
            (store / 'base' / 'part.parquet').write_bytes(b'')
            summary, calls = self.run_seq(store, 'fit,publish,verify')
            self.assertEqual([s['status'] for s in summary['steps'].values()], ['ok', 'ok', 'ok'])
            fit, publish, verify = calls
            self.assertIn('verificar_release.py', verify[-1])
            self.assertIn('releases/atlas30/r1', verify[-1])
            self.assertEqual(fit[-1], 'fit')
            self.assertIn('--set-current', publish)
            self.assertEqual(publish[publish.index('--similarity-model') + 1], str(Path(tmp) / 'model.joblib'))
            failed, calls = self.run_seq(store, 'fit,publish,verify', fail={'motor_similitud.py'})
            self.assertEqual(failed['steps']['publish']['status'], 'skipped')
            self.assertEqual(failed['steps']['verify']['status'], 'skipped')
            self.assertEqual(len(calls), 1)

    def test_unknown_step_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(SystemExit):
            self.run_seq(Path(tmp) / 'store', 'build,nope')


if __name__ == '__main__':
    unittest.main()
