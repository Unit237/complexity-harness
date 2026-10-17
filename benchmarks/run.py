"""Reproducible corpus check. Downloads source archives; never runs repo code.

Use the dev extra for pinned independent analyzers. Archives stay in the caller's
cache; only measurements and immutable source links enter the report.
"""
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import json
from pathlib import Path,PurePosixPath
import tarfile
import urllib.request

import lizard
from importlib.metadata import version
from complexity_harness.burden import ANALYZER,CONTROL_LANGUAGES,STRUCTURAL_LANGUAGES,measure_snapshot
from complexity_harness.complexity_evidence import pack_file
from complexity_harness.complexity_languages import classify_path
from complexity_harness.polyglot_analyzer import analyze_bytes
from complexity_harness.source_scope import source_policy,_is_excluded,content_fingerprint


def download(row,cache):
    path=cache/(row['repository'].replace('/','--')+'--'+row['commit']+'.tar.gz')
    if not path.exists():
        request=urllib.request.Request(row['archive_url'],headers={'User-Agent':'complexity-calibration'})
        partial=path.with_suffix('.partial')
        with urllib.request.urlopen(request,timeout=90) as response,partial.open('wb') as target:
            total=0
            while chunk:=response.read(1024*1024):
                total+=len(chunk)
                if total>128*1024*1024:raise ValueError('Archive exceeds the validation download bound')
                target.write(chunk)
        partial.replace(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if row.get('archive_sha256') and row['archive_sha256']!=digest:
        raise ValueError('Pinned archive digest changed: '+row['repository'])
    return path,digest


def capture(row,archive_path):
    files,inventory,unknown,hashes=[],[],[],{}
    discrepancies,language_counts=[],defaultdict(Counter)
    directories,patterns,scope_hash=source_policy({})
    with tarfile.open(archive_path,'r:gz') as archive:
        members=[m for m in archive if m.isfile() or m.issym() or m.islnk()]
        if len(members)>250000:raise ValueError('Corpus exceeds bounded inventory')
        total=0
        for member in sorted(members,key=lambda m:m.name):
            relative=PurePosixPath(*PurePosixPath(member.name).parts[1:])
            if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative):raise ValueError('Unsafe archive member')
            path=str(relative);classification=classify_path(path)
            total+=member.size
            if total>512*1024*1024:raise ValueError('Expanded corpus exceeds validation bound')
            # Link targets are metadata, never followed or materialized.
            data=member.linkname.encode() if not member.isfile() else archive.extractfile(member).read()
            entry={'path':path,'sha256':content_fingerprint(data),**classification}
            if _is_excluded(relative,directory_names=directories,patterns=patterns,workspace_path=None):entry.update(kind='excluded',reason='Repository exclusion policy')
            if entry['kind'] in {'source','unknown','opaque'}:
                language=entry['language']
                if member.isfile() and len(data)<=512*1024 and language in CONTROL_LANGUAGES|STRUCTURAL_LANGUAGES:
                    try:metric=analyze_bytes(data,relative_path=path,language=language)
                    except UnicodeDecodeError:metric=None
                    if metric:
                        files.append(pack_file(asdict(metric)))
                        if not metric.parse_error and language in CONTROL_LANGUAGES and language not in {'dart','bash'}:
                            reference=lizard.analyze_file.analyze_source_code(path,data.decode('utf-8')).function_list
                            own_by_line=defaultdict(list);ref_by_line=defaultdict(list)
                            for f in metric.functions:own_by_line[f.line].append(f)
                            for f in reference:ref_by_line[f.start_line].append(f)
                            count=language_counts[language];count['own_functions']+=len(metric.functions);count['reference_functions']+=len(reference)
                            for line in own_by_line.keys() | ref_by_line.keys():
                                if len(own_by_line[line])!=1 or len(ref_by_line[line])!=1:
                                    count['unpaired_own']+=len(own_by_line[line]);count['unpaired_reference']+=len(ref_by_line[line]);continue
                                own,ref=own_by_line[line][0],ref_by_line[line][0]
                                count['paired']+=1;difference=own.cyclomatic-ref.cyclomatic_complexity
                                count['equal']+=difference==0;count['within_one']+=abs(difference)<=1
                                if difference:
                                    discrepancies.append({'language':language,'path':path,'line':line,'symbol':own.symbol,'ours':own.cyclomatic,'reference':ref.cyclomatic_complexity,'difference':difference,
                                        'own_end_line':own.end_line,'reference_end_line':ref.end_line,
                                        'nested_units':sum(line < f.line <= own.end_line for f in metric.functions),
                                        'url':f"https://github.com/{row['repository']}/blob/{row['commit']}/{path}#L{line}"})
                    else:unknown.append(path);hashes[path]=entry['sha256']
                else:unknown.append(path);hashes[path]=entry['sha256']
            inventory.append(entry)
    snapshot={'schema_version':'complexity-snapshot-v1','repository':{'name':row['repository'],'commit':row['commit'],'clean':True,'provenance':{'archive_sha256':row['archive_sha256'],'url':row['archive_url']}},
        'files':files,'coverage':{'analyzer':ANALYZER,'scope_hash':scope_hash,'inventory_policy':'all-files-v2','inventory':inventory,'unsupported_paths':unknown,'unsupported_hashes':hashes,'inventory_complete':True,'eligible_files':len(files)+len(unknown)}}
    try:
        measured=measure_snapshot(snapshot)
    except ValueError as exc:
        # Resource limits are outcomes, never a truncated or healthy baseline.
        if str(exc) != 'Function inventory exceeds the bounded snapshot limit':
            raise
        return snapshot, {'repository':row['repository'],'commit':row['commit'],'cohort':row['cohort'],
            'role':row['role'],'archive_sha256':row['archive_sha256'],'status':'resource_limited',
            'reason':str(exc),'score':None,'summary':None,'factors':{},
            'inventory_files':len(inventory),'eligible_files':len(files)+len(unknown),
            'reference':{k:dict(v) for k,v in language_counts.items()},'discrepancies':discrepancies}
    return snapshot,{'repository':row['repository'],'commit':row['commit'],'cohort':row['cohort'],'role':row['role'],'archive_sha256':row['archive_sha256'],
        'status':'measured' if measured['score'] is not None else 'diagnostic_only','score':measured['score'],'factors':measured['factors'],'coverage':{k:v for k,v in measured['coverage'].items() if k not in {'unsupported_hashes','excluded_fingerprint','unmeasured'}},
        'summary':measured['summary'],'reference':{k:dict(v) for k,v in language_counts.items()},'discrepancies':discrepancies,
        'hotspots':measured['findings'][:12]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',default=str(Path(__file__).with_name('repositories-v1.json')))
    parser.add_argument('--cache',required=True);parser.add_argument('--output',required=True);parser.add_argument('--write-digests',action='store_true')
    args=parser.parse_args();manifest=json.loads(Path(args.manifest).read_text());cache=Path(args.cache);cache.mkdir(parents=True,exist_ok=True)
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    rows=manifest['repositories']
    with ThreadPoolExecutor(max_workers=4) as pool:archives=list(pool.map(lambda row:download(row,cache),rows))
    for row,(_,digest) in zip(rows,archives):row['archive_sha256']=digest
    if args.write_digests:Path(args.manifest).write_text(json.dumps(manifest,indent=2)+'\n')
    report={'schema_version':'complexity-corpus-report-v1','analyzer':ANALYZER,'reference':{'name':'lizard','version':version('lizard'),'pairing':'unique start line; unmatched routines reported separately; conventions may differ'},'repositories':[]}
    for row,(archive,digest) in zip(rows,archives):
        row['archive_sha256']=digest
        snapshot,result=capture(row,archive)
        name=row['repository'].replace('/','--')
        (output/(name+'.snapshot.json')).write_text(json.dumps(snapshot,separators=(',',':'))+'\n')
        report['repositories'].append(result)
        print(json.dumps({k:result[k] for k in ['repository','score','summary']}),flush=True)
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    if args.write_digests:Path(args.manifest).write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
