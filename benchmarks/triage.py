"""Inspect the largest reference disagreement per language; do not assume an oracle.

Reads pinned archives and our saved snapshots. No customer code is executed.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import tarfile
import lizard


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',required=True);parser.add_argument('--cache',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();report_path=Path(args.report);report=json.loads(report_path.read_text())
    selected={}
    for repo in report['repositories']:
        if repo['status']=='resource_limited':continue
        for item in repo['discrepancies']:
            if item['language'] not in selected or abs(item['difference'])>abs(selected[item['language']][1]['difference']):selected[item['language']]=(repo,item)
    rows=[]
    for language,(repo,item) in sorted(selected.items()):
        archive=Path(args.cache)/(repo['repository'].replace('/','--')+'--'+repo['commit']+'.tar.gz')
        with tarfile.open(archive) as source:
            member=next(m for m in source if '/'.join(m.name.split('/')[1:])==item['path'])
            data=source.extractfile(member).read().decode('utf-8')
        snapshot=json.loads((report_path.parent/(repo['repository'].replace('/','--')+'.snapshot.json')).read_text())
        file=next(f for f in snapshot['files'] if f['path']==item['path'])
        own=next(f for f in file['functions'] if f['line']==item['line'])
        ref=next(f for f in lizard.analyze_file.analyze_source_code(item['path'],data).function_list if f.start_line==item['line'])
        nested=[f for f in file['functions'] if own['line']<f['line']<=own['end_line']]
        folded=own['cyclomatic']+sum(f['cyclomatic']-1 for f in nested)
        rows.append({**item,'repository':repo['repository'],'own_end_line':own['end_line'],'reference_end_line':ref.end_line,
            'nested_units':len(nested),'folded_complexity':folded,'fully_explained_by_nested_ownership':folded==ref.cyclomatic_complexity,
            'branch_kinds':dict(Counter(b['kind'] for b in own['branches'])),
            'source_excerpt':data.splitlines()[item['line']-1:min(item['line']+2,len(data.splitlines()))]})
    Path(args.output).write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(rows,indent=2))

if __name__=='__main__':main()
