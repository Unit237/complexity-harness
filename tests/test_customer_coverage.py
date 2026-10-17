"""Customer syntax and formats use shared parsers, never repository exceptions."""
from pathlib import Path
import json
import pytest
from complexity_harness.burden import measure_snapshot, reduction_evidence, MAX_SOURCE_BYTES
from complexity_harness.complexity_languages import classify_path
from complexity_harness.polyglot_analyzer import analyze_bytes
from complexity_harness.scanner import scan_repository


CASES=json.loads((Path(__file__).parents[1]/'benchmarks/customer-syntax-v1.json').read_text())

@pytest.mark.parametrize('case',CASES,ids=lambda case:case['path']+'-'+case['language'])
def test_real_world_syntax_retains_every_explicit_decision(case):
    path,language,source,decisions=(case[k] for k in ("path","language","source","decisions"))
    metric=analyze_bytes(source.encode(),relative_path=path,language=language)
    assert not metric.parse_error,metric.parse_error
    assert sum(f.cyclomatic-1 for f in metric.functions)==decisions
    assert all(1<=branch.line<=metric.lines for f in metric.functions for branch in f.branches)


@pytest.mark.parametrize('path,language',[
 ('Fastfile','ruby'),('Appfile','ruby'),('.metadata','yaml'),('settings.xcconfig','properties'),
 ('app.properties','properties'),('project.pbxproj','openstep'),('config.ini','config'),
 ('CMakeLists.txt','cmake'),('schema.proto','protobuf'),('Info.plist','xml'),
 ('Launch.storyboard','xml'),('Privacy.xcprivacy','xml'),('App.entitlements','xml'),
 ('contents.xcworkspacedata','xml'),('Scheme.xcscheme','xml'),('runner.manifest','xml'),
 ('main.tfvars.example','hcl'),
])
def test_format_detection_covers_customer_project_and_build_files(path,language):
    assert classify_path(path)=={'kind':'source','language':language,'reason':None}


def measure(root,sha):
    payload=scan_repository(root).as_dict();payload['repository'].update(commit=sha*40,clean=True)
    return measure_snapshot(payload)


def test_embedded_scripts_are_scored_once_at_original_source_lines_with_separate_diagnostics(tmp_path):
    (tmp_path/'page.html').write_text('<html>\n<body><div><section><main><p>Hello</p></main></section></div>\n<script>\nfunction f(x) { if(x) return 1; return 0; }\n</script>\n<script type="application/ld+json">{"a":{"b":{"c":{"d":1}}}}</script>\n<style>@container card (width > 20px) { .a { & > b { color:red; } } }</style>\n</body></html>')
    result=measure(tmp_path,'a')
    assert result['coverage']['complete'] and result['coverage']['score_percent']==100
    assert result['coverage']['scored_files']==1 and result['summary']['decisions']==1
    assert result['factors']['structure']['score'] is None and result['factors']['structure']['decisions']>0
    assert result['files'][0]['metric_family']=='control_flow'
    metric=scan_repository(tmp_path).files[0]
    assert metric.functions[0].line==4 and metric.functions[0].branches[0].line==4
    assert result['summary']['functions']==1  # JSON and CSS cannot dilute the score.
    (tmp_path/'page.html').write_text('<script type="application/ld+json">{}</script><style>.x{color:red}</style>')
    assert measure(tmp_path,'b')['score'] is None


def test_private_configuration_is_accounted_for_and_protected_without_pretending_it_is_code(tmp_path):
    (tmp_path/'app.js').write_text('function f(x,y) { if(x) return 1; if(y) return 2; return 0; }')
    (tmp_path/'.env').write_text('API_KEY=private-value')
    before=measure(tmp_path,'a')
    assert before['coverage']['inventory_files']==2 and before['coverage']['eligible_files']==1
    assert before['coverage']['complete']
    (tmp_path/'app.js').write_text('function f(x) { if(x) return 1; return 0; }')
    assert reduction_evidence(before,measure(tmp_path,'b'))['comparable']
    (tmp_path/'.env').write_text('API_KEY=changed-private-value')
    assert not reduction_evidence(before,measure(tmp_path,'b'))['comparable']


def test_source_over_the_old_512kb_limit_is_measured_and_the_new_limit_stays_explicit(tmp_path):
    (tmp_path/'config.json').write_text(json.dumps({'large':'x'*(600*1024)}))
    assert measure(tmp_path,'a')['coverage']['complete']
    (tmp_path/'huge.js').write_text(' '*MAX_SOURCE_BYTES+'function f() {}')
    result=measure(tmp_path,'b')
    assert result['coverage']['unsupported_paths']==['huge.js']
    assert str(MAX_SOURCE_BYTES) in result['coverage']['unmeasured'][0]['reason']
    from complexity_harness.source_scope import content_fingerprint
    assert result['coverage']['unsupported_hashes']['huge.js']==content_fingerprint((' '*MAX_SOURCE_BYTES+'function f() {}').encode())


def test_invalid_or_unknown_embedded_languages_never_produce_partial_healthy_scores():
    for source in ['<script>const f = x => x ? 1 : ;</script>', '<script type="text/customer-language">choose x</script>', '<script lang="python">x = 1</script>']:
        metric=analyze_bytes(source.encode(),relative_path='page.html',language='html')
        assert metric.parse_error and not metric.functions


def test_inline_handlers_and_javascript_urls_cannot_hide_moved_decisions(tmp_path):
    (tmp_path/'page.html').write_text('<button onclick="if (x &amp;&amp; y) {&#10;go(); }">Go</button>\n<a href="javascript:x ? go() : stop()">Go</a>')
    result=measure(tmp_path,'a')
    assert result['summary']['decisions']==3 and result['coverage']['score_percent']==100
    metric=scan_repository(tmp_path).files[0]
    assert [branch.line for branch in metric.functions[0].branches]==[1,1]
    assert metric.functions[1].branches[0].line==2
    assert metric.functions[0].end_line==1  # Entity newlines do not invent source lines.


def test_computed_method_names_run_in_the_enclosing_scope_and_parameters_in_the_method():
    metric=analyze_bytes(b'const obj = {[x ? "a" : "b"](y = true) { return x && y; }};',relative_path='scope.js',language='javascript')
    assert not metric.parse_error
    assert {f.symbol:f.cyclomatic-1 for f in metric.functions}=={'<ObjectMethod>':2,'<module>':1}
