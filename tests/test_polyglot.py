"""Independent small programs cover the declared adapter surface."""
from dataclasses import asdict
import copy
import pytest
from complexity_harness.burden import ANALYZER, CONTROL_LANGUAGES, STRUCTURAL_LANGUAGES, measure_snapshot, reduction_evidence
from complexity_harness.polyglot_analyzer import analyze_bytes
from complexity_harness.scanner import scan_repository

PROGRAMS = {
 'javascript':('app.mjs','const choose = a => { if (a) return 1; return 0; };'),
 'typescript':('app.ts','function choose(a: boolean): number { if (a) return 1; return 0; }'),
 'tsx':('app.tsx','const Choose = (a: boolean) => { if (a) return <div/>; return null; };'),
 'c':('app.c','int choose(int a) { if (a) return 1; return 0; }'),
 'c_header':('app.h','inline int choose(int a) { if (a) return 1; return 0; }'),
 'cpp':('app.cc','int choose(int a) { if (a) return 1; return 0; }'),
 'csharp':('app.cs','class App { int Choose(bool a) { if(a) return 1; return 0; } }'),
 'java':('App.java','class App { int choose(boolean a) { if(a) return 1; return 0; } }'),
 'go':('app.go','package app\nfunc choose(a bool) int { if a { return 1 }; return 0 }'),
 'rust':('app.rs','fn choose(a: bool) -> i32 { if a { 1 } else { 0 } }'),
 'ruby':('app.rb','def choose(a)\n if a\n  1\n else\n  0\n end\nend\n'),
 'php':('app.php','<?php function choose($a) { if ($a) return 1; return 0; }'),
 'kotlin':('app.kt','fun choose(a: Boolean): Int { return if (a) 1 else 0 }'),
 'swift':('app.swift','func choose(_ a: Bool) -> Int { if a { return 1 }; return 0 }'),
 'dart':('app.dart','int choose(bool a) { if(a) return 1; return 0; }'),
 'bash':('app.sh','choose() { if [ "$1" = yes ]; then echo 1; else echo 0; fi; }'),
 'lua':('app.lua','function choose(a) if a then return 1 else return 0 end end'),
 'python':('app.py','def choose(a):\n    return 1 if a else 0\n'),
}

@pytest.mark.parametrize('language',sorted(PROGRAMS))
def test_control_flow_adapters_reconstruct_a_real_branch(language):
 path,source=PROGRAMS[language]
 metric=analyze_bytes(source.encode(),relative_path=path,language=language)
 assert not metric.parse_error, (language,metric.parse_error)
 assert sum(f.cyclomatic-1 for f in metric.functions)+sum(b.contribution for b in metric.unattributed_branches)==1
 assert len(metric.functions)>=1
 assert all(f.branches for f in metric.functions if f.cyclomatic>1)
 assert set(PROGRAMS)==CONTROL_LANGUAGES

STRUCTURES = {
 'hcl':('main.tf','resource "x" "y" { nested { nested { nested { x = 1 } } } }'),
 'sql':('query.sql','SELECT * FROM a JOIN b ON a.id=b.id WHERE a.x AND b.x;'),
 'css':('app.css','@media screen { .a { color: red; } }'),
 'json':('config.json','{"a":{"b":{"c":{"d":1}}}}'),
 'yaml':('config.yml','a:\n  b:\n    c:\n      d:\n        value: 1\n'),
 'html':('index.html','<html><body><div><section><p>Hi</p></section></div></body></html>'),
 'xml':('app.xml','<root><a><b><c><d/></c></b></a></root>'),
 'dockerfile':('Dockerfile','FROM alpine\nRUN echo hello\n'),
 'make':('Makefile','all:\n\techo hello\n'),
 'toml':('config.toml','a = [[[[[1]]]]]\n'),
 'graphql':('app.graphql','query { user { friends { friends { name } } } }'),
 'cmake':('CMakeLists.txt','if(ON)\n message(STATUS "yes")\nendif()\n'),
 'protobuf':('app.proto','syntax = "proto3"; message A { string name = 1; }'),
 'config':('app.ini','[application]\nname = customer\n'),
 'properties':('app.properties','application.name=customer\n'),
 'openstep':('project.pbxproj','{ objects = { abc = { isa = PBXProject; }; }; }'),
}

@pytest.mark.parametrize('language',sorted(STRUCTURES))
def test_declarative_adapters_report_structure_as_a_separate_factor(language):
 path,source=STRUCTURES[language]
 metric=analyze_bytes(source.encode(),relative_path=path,language=language)
 assert not metric.parse_error,(language,metric.parse_error)
 assert metric.metric_family=='structure'
 assert metric.structural['containers']>0
 assert metric.functions[0].cyclomatic==1+sum(b.contribution for b in metric.functions[0].branches)
 assert set(STRUCTURES)==STRUCTURAL_LANGUAGES


def test_customer_inventory_includes_unknown_dsl_declarative_code_and_unusual_extensions(tmp_path):
 for language in ('python','javascript','cpp','bash'):
  path,source=PROGRAMS[language];(tmp_path/path).write_text(source)
 for language in ('hcl','sql','yaml'):
  path,source=STRUCTURES[language];(tmp_path/path).write_text(source)
 (tmp_path/'legacy.cbl').write_text('       IDENTIFICATION DIVISION.')
 (tmp_path/'rules.customerlang').write_text('CUSTOM CUSTOMER POLICY')
 (tmp_path/'component.vue').write_text('<script>if (ready) go()</script>')
 (tmp_path/'.env').write_text('SECRET=do-not-read-with-parser')
 (tmp_path/'README.md').write_text('Customer repository')
 payload=scan_repository(tmp_path).as_dict();payload['repository'].update(clean=True,commit='a'*40)
 result=measure_snapshot(payload)
 assert result['coverage']['inventory_files']==12
 assert result['coverage']['eligible_files']==10
 assert result['coverage']['analyzed_files']==7
 assert result['coverage']['percent']==70
 assert set(result['coverage']['unsupported_paths'])=={'legacy.cbl','rules.customerlang','component.vue'}
 assert result['coverage']['inventory_counts']['opaque']==1
 assert set(result['factors'])=={'control_flow','structure'}
 assert result['score']==result['factors']['control_flow']['score']
 assert result['factors']['structure']['score'] is None
 assert result['factors']['structure']['status']=='diagnostic_only'
 omitted=copy.deepcopy(payload);omitted['coverage']['unsupported_paths'].remove('rules.customerlang')
 with pytest.raises(ValueError,match='Every eligible'):
  measure_snapshot(omitted)


def test_invalid_embedded_source_and_invalid_dialects_are_unmeasured():
 for lang,path,source in [('html','page.html','<script>function broken(</script>'),('javascript','broken.js','function broken(')]:
  metric=analyze_bytes(source.encode(),relative_path=path,language=lang)
  assert metric.parse_error and not metric.functions


def test_closure_and_module_decisions_are_owned_once():
 metric=analyze_bytes(b'if (ready) go(); const outer = () => { const inner = x => x ? 1 : 0; return inner; };',relative_path='app.mjs',language='javascript')
 assert not metric.parse_error
 assert sum(f.cyclomatic-1 for f in metric.functions)==2
 assert sorted(f.cyclomatic for f in metric.functions)==[1,2,2]


def _measured(root,sha):
 payload=scan_repository(root).as_dict();payload['repository'].update(clean=True,commit=sha*40)
 return measure_snapshot(payload)


def test_reduction_cannot_hide_in_unknown_excluded_source_or_another_factor(tmp_path):
 (tmp_path/'app.mjs').write_text('function choose(a,b) { if (a) return 1; if (b) return 2; return 0; }')
 (tmp_path/'customer.dsl').write_text('UNCHANGED')
 (tmp_path/'config.json').write_text('{}')
 (tmp_path/'generated.min.js').write_text('UNCHANGED')
 before=_measured(tmp_path,'a')
 (tmp_path/'app.mjs').write_text('function choose(a) { if (a) return 1; return 0; }')
 assert reduction_evidence(before,_measured(tmp_path,'b'))['comparable']
 (tmp_path/'customer.dsl').write_text('MOVED DECISION')
 assert not reduction_evidence(before,_measured(tmp_path,'b'))['comparable']
 (tmp_path/'customer.dsl').write_text('UNCHANGED')
 (tmp_path/'generated.min.js').write_text('MOVED DECISION')
 assert not reduction_evidence(before,_measured(tmp_path,'b'))['comparable']
 (tmp_path/'generated.min.js').write_text('UNCHANGED')
 (tmp_path/'config.json').write_text('{"a":{"b":{"c":{"d":1}}}}')
 assert not reduction_evidence(before,_measured(tmp_path,'b'))['comparable']


def test_missing_or_wrong_parser_bundle_is_explicitly_unmeasured(monkeypatch):
 monkeypatch.setattr('complexity_harness.polyglot_analyzer.version',lambda package:'unexpected')
 metric=analyze_bytes(b'int choose(int a) { if(a) return 1; }',relative_path='app.c',language='c')
 assert metric.parse_error and not metric.functions


def test_flat_scalar_declarations_are_not_reported_as_structural_fanout():
 source=':root { '+''.join(f'--color-{i}: red;' for i in range(100))+' }'
 metric=analyze_bytes(source.encode(),relative_path='tokens.css',language='css')
 assert not metric.parse_error
 assert metric.structural['fanout_points']==0
 assert metric.functions[0].cyclomatic==1
 nested=analyze_bytes(b'{"a":{"b":{"c":{"d":{}}}}}',relative_path='schema.json',language='json')
 assert nested.structural['nesting_points']>0


@pytest.mark.parametrize('language,source,decisions',[
 ('java','class A { int f(int x) { switch(x) { case 1: return 1; case 2: return 2; default: return 0; } } }',2),
 ('csharp','class A { int F(int x) { switch(x) { case 1: return 1; case 2: return 2; default: return 0; } } }',2),
 ('kotlin','fun f(x: Int): Int { return when(x) { 1 -> 1; 2 -> 2; else -> 0 } }',2),
 ('swift','func f(_ x: Int) -> Int { switch x { case 1: return 1; case 2: return 2; default: return 0 } }',2),
 ('dart','int f(int x) { switch(x) { case 1: return 1; case 2: return 2; default: return 0; } }',2),
 ('go','package a\nfunc f(x int) int { switch x { case 1: return 1; case 2: return 2; default: return 0 }; }',2),
 ('rust','fn f(x: i32) -> i32 { match x { 1 => 1, 2 => 2, _ => 0 } }',3),
 ('lua','function f(x,y) if x and y then return 1 end return 0 end',2),
 ('ruby','def f(x,y)\n if x && y\n  1\n end\nend',2),
 ('bash','f() { if test x && test y; then echo 1; elif test z; then echo 2; fi; }',3),
 ('javascript','const f = x => x?.a ?? 0;',2),
 ('javascript','function f(xs) { for (const x of xs) { while(x.ok && x.ready) { try { x.go(); } catch(e) { return 0; } } } }',4),
])
def test_switch_boolean_and_loop_constructs_cannot_disappear_from_native_evidence(language,source,decisions):
 metric=analyze_bytes(source.encode(),relative_path=PROGRAMS[language][0],language=language)
 assert not metric.parse_error
 assert sum(f.cyclomatic-1 for f in metric.functions)==decisions


def test_reports_and_recorded_fixtures_are_classified_and_protected_without_becoming_hotspots(tmp_path):
 (tmp_path/'app.mjs').write_text('function choose(x,y) { if(x) return 1; if(y) return 2; return 0; }')
 (tmp_path/'artifacts').mkdir();report=tmp_path/'artifacts/report.json'
 report.write_text('{"a":{"b":{"c":{"d":{"e":{}}}}}}')
 (tmp_path/'app.g.dart').write_text('Generated source')
 before=_measured(tmp_path,'a')
 assert before['coverage']['eligible_files']==1
 assert before['coverage']['inventory_counts']['data']==1
 assert before['coverage']['inventory_counts']['generated']==1
 assert all(f['metric_family']=='control_flow' for f in before['files'])
 (tmp_path/'app.mjs').write_text('function choose(x) { if(x) return 1; return 0; }')
 assert reduction_evidence(before,_measured(tmp_path,'b'))['comparable']
 report.write_text('{}')
 assert not reduction_evidence(before,_measured(tmp_path,'b'))['comparable']
