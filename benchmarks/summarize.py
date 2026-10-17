"""Reduce corpus receipts into a reviewable, versioned validation disclosure."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
from complexity_harness.burden import ANALYZER,VERSION,measure_snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',required=True);parser.add_argument('--before',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();report_path=Path(args.report);report=json.loads(report_path.read_text());before=json.loads(Path(args.before).read_text())
    previous={r['repository']:r for r in before['repositories']}
    languages=defaultdict(Counter);rows=[]
    for row in report['repositories']:
        for language,counts in row['reference'].items():languages[language].update(counts)
        result={key:row[key] for key in ['repository','commit','role','status','archive_sha256']}
        result['url']=f"https://github.com/{row['repository']}/tree/{row['commit']}"
        if row['status']=='resource_limited':
            result.update(score=None,reason=row['reason'],eligible_files=row['eligible_files'],inventory_files=row['inventory_files'])
        else:
            snapshot=json.loads((report_path.parent/(row['repository'].replace('/','--')+'.snapshot.json')).read_text())
            measured=measure_snapshot(snapshot);coverage=measured['coverage']
            assert measured['score']==row['score']
            result.update(score=row['score'],before_score=previous[row['repository']]['score'],
                inventory_files=coverage['inventory_files'],eligible_files=coverage['eligible_files'],analyzed_files=coverage['analyzed_files'],
                scored_files=coverage['scored_files'],diagnostic_files=coverage['diagnostic_files'],score_coverage_percent=coverage['score_percent'],
                parse_error_files=len(coverage['parse_error_paths']),unsupported_files=len(coverage['unsupported_paths']),
                programming_units=measured['summary']['functions'],hotspots=measured['summary']['hotspots'])
        rows.append(result)
    benchmark=Path(__file__).parent
    oracle=json.loads((benchmark/'construct-oracle-v1.json').read_text())
    result={'schema_version':'complexity-calibration-v1','measurement_version':VERSION,'analyzer':ANALYZER,'evaluated_on':'2026-10-17',
        'source':'Pinned public repositories used as customer stand-ins; no private customer repositories or repository code execution.',
        'method':'Reference anchors and monotonicity checks, construct oracles, corpus coverage, and an independent analyzer comparison. This is not a statistical prediction of engineering difficulty.',
        'summary':{'repositories':len(rows),'scored_repositories':sum(r['status']=='measured' for r in rows),
            'diagnostic_only_repositories':sum(r['status']=='diagnostic_only' for r in rows),'resource_limited_repositories':sum(r['status']=='resource_limited' for r in rows),
            'construct_cases':len(oracle['cases']),'programming_languages':17,'declarative_formats':11,
            'analyzed_files':sum(r.get('analyzed_files',0) for r in rows),'scored_programming_units':sum(r.get('programming_units',0) for r in rows),
            'old_structure_dominated':sum(r.get('factors',{}).get('structure',{}).get('score',-1)==r['score'] for r in before['repositories'])},
        'reference':{**report['reference'],'counts':{k:dict(v) for k,v in sorted(languages.items())},
            'interpretation':'Agreement is a diagnostic, not accuracy. Start-line pairing may align different spans. Closures, optional type syntax, preprocessor and exception conventions differ; inspect reference-triage.json and source before assigning fault.'},
        'limitations':['Public stand-ins cover common product types, not every customer, language, dialect or framework.',
            'No human-rated maintainability, defect-rate or engineering-time outcome labels. Bands, target and weights are investigation policy, not empirical quality grades.',
            'Corpus splits were declared before execution but all results were inspected; no blind holdout performance claim.',
            'Declarative structure lacks a validated common scale and remains diagnostic-only. Unsupported syntax stays visibly unmeasured.',
            'Python syntax uses the 3.11 grammar across producer runtimes. Python 3.12+ syntax such as type aliases remains unmeasured until a versioned grammar upgrade.',
            'The complete Skaffold corpus exceeds the 100,000-unit snapshot limit. No truncated baseline or score is published.',
            'Scores saturate at 24 decisions per unit. Raw branch evidence and hotspots retain larger counts; nesting and essential domain logic require review.'],
        'evidence_hashes':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in {
            'repository_manifest':benchmark/'repositories-v1.json','construct_oracle':benchmark/'construct-oracle-v1.json',
            'before_report':Path(args.before),'after_report':report_path}.items()},'repositories':rows}
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary']))

if __name__=='__main__':main()
