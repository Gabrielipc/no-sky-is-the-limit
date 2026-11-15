from argparse import Namespace
import json

import numpy as np
import pytest

from pipelines import jezero_evaluation as ev, jezero_spectral as sp, similarity_ml as sim
from scripts import piloto_jezero as cli


def test_stratified_design_is_exact_and_records_the_actual_probability():
    rows = [
        {'region_id': str(i), 'block': 'rare' if i < 2 else 'common',
         'relief_p95_p05_m': i, 'precip_annual_mm_cmg': None if i == 0 else 100}
        for i in range(200)
    ]
    derived = sp.design_sample(rows, 10, 17)
    assert derived == sp.design_sample(rows, 10, 17)
    assert len(derived) == 10
    assert derived['0']['inclusion_probability'] == 1
    assert derived['1']['inclusion_probability'] == 1
    assert all(0 < r['inclusion_probability'] <= 1 for r in derived.values())
    with pytest.raises(ValueError, match='estratos'):
        sp.design_sample(rows, 1, 17)


def observation(rid, body, value, *, role='background', scene='a', partition='fit'):
    return {
        'region_id': rid, 'role': role, 'scene_id': scene, 'body': body, 'partition': partition,
        'inclusion_probability': .2, 'geologic_unit': scene,
        'indicators': {f: {'p50': value + i, 'status': 'measured_absent' if i == 0 else 'measured'}
                       for i, f in enumerate(sp.INDICATORS)},
    }


def observations():
    controls = [observation(f'control{i}', body, i + offset, role='control', scene=scene)
                for body in ('Earth', 'Mars') for i in range(10) for offset, scene in ((0, 'a'), (.5, 'b'))]
    earth = [observation(f'E{i}', 'Earth', i / 200) for i in range(200)]
    mars = [observation(f'M{i}', 'Mars', i / 100, scene='a' if i % 2 else 'b') for i in range(100)]
    return controls + earth + mars + [observation('jezero', 'Mars', .5, role='reference')]


def test_spectral_fit_counts_real_windows_and_accepts_measured_absence():
    rows = observations()
    metric, evidence = ev.fit_spectral(rows)
    assert evidence['pass']
    assert all(e['earth'] == 200 and e['mars'] == 100 for e in evidence['support'].values())
    center = observation('test', 'Earth', .5, partition='test')
    unobserved = dict(center, indicators={f: {'p50': 0, 'status': 'unobserved_by_product'}
                                          for f in sp.INDICATORS})
    assert np.isfinite(metric.score([center])[0])
    assert np.isnan(metric.score([unobserved])[0])
    rows = [r for r in rows if r['region_id'] != 'E199'] + [center]
    metric, evidence = ev.fit_spectral(rows)
    assert metric is None
    assert all(e['earth'] == 199 for e in evidence['support'].values())


def test_held_out_recovery_executes_unique_lists_at_equal_budget():
    frame = [{'region_id': str(i), 'block': str(i % 3), 'inclusion_probability': .5} for i in range(100)]
    topography = {str(i): i for i in range(100)}
    spectrum = {str(i): -i for i in range(100)}
    report = ev.retrieval_metrics(frame, topography, spectrum, spectrum, 27)
    assert report['pass']
    assert report['topography'] == {'unique': 27, 'recall': 0}
    assert report['union'] == {'unique': 27, 'recall': 1}
    assert report['outside_topography'] > 0
    assert ev.proposal_union(frame, topography, spectrum, 27, 2, topographic=False)[0] == '99'
    assert ev.combine({'a': .2, 'b': .02}, {'a': .8}) == {'a': pytest.approx(.35)}


def test_blind_review_requires_two_reviewers_and_uses_only_held_out_common_windows():
    frame = [{'region_id': f'b{b}-{i}', 'block': b} for b in range(3) for i in range(25)]
    truth = {row['region_id']: i % 25 for i, row in enumerate(frame)}
    topography = {rid: n for rid, n in truth.items()}
    spectral = {rid: -n for rid, n in truth.items()}
    rankings = {'topography': topography, 'combined': spectral, 'spectral': spectral, 'r2c': topography}
    reviews = [dict(region_id=rid, reviewer=reviewer, score=n // 7, source='field-map')
               for rid, n in truth.items() for reviewer in ('A', 'B')]
    assert ev.relevance_metrics(frame, rankings, reviews)['ci95'][0] > 0
    assert not ev.relevance_metrics(frame, rankings, reviews[:-1])['pass']


def test_diagnostic_cannot_be_published_and_release_is_immutable(tmp_path):
    report = tmp_path / 'report.json'
    measurements = tmp_path / 'measurements.json'
    measurements.write_text('{"observations": []}')
    design = tmp_path / 'design.json'
    design.write_text('{"scenes": {}, "holdouts": [], "samples": {}}')
    args = Namespace(report=report, design=design, measurements=measurements,
                     root=tmp_path / 'releases', version='jezero-r3-test')
    output = {'format': cli.FORMAT, 'status': 'diagnostic'}
    cli.write(report, output)
    with pytest.raises(ValueError, match='diagnóstico'):
        cli.publish(args)
    output['status'] = 'publishable_experiment'
    output.update({key: {'pass': True} for key in ('support', 'retrieval', 'relevance', 'stability')})
    output['measurements_sha256'] = cli.digest(measurements)
    output['design_sha256'] = cli.digest(design)
    cli.write(report, output)
    assert cli.publish(args)['status'] == 'experimental'
    with pytest.raises(ValueError, match='existe'):
        cli.publish(args)
    assert [path.name for path in args.root.iterdir()] == [args.version]


def test_reference_center_must_match_the_spectral_footprint(tmp_path):
    path = tmp_path / 'reference.json'
    path.write_text(json.dumps({'longitude': 77.45, 'latitude': 18.44}))
    with pytest.raises(ValueError, match='centro'):
        cli.make_reference(path, {'longitude': 77.41, 'latitude': 18.49}, sim.load_spec())
