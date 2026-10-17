"""GitHub Actions expressions and inline scripts, parsed without execution."""
from dataclasses import replace
from importlib.metadata import version
import hashlib
import json
import re
from .models import BranchEvidence,FileMetric,FunctionMetric

TOKEN=re.compile(r"\s+|'(?:[^']|'')*'|[+-]?(?:0[xX][\da-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)|[A-Za-z_][\w-]*|&&|\|\||==|!=|<=|>=|[!<>().*\[\],]")
PRECEDENCE={'||':1,'&&':2,'==':3,'!=':3,'<':4,'<=':4,'>':4,'>=':4}
FUNCTIONS=set('contains startswith endswith format join tojson fromjson hashfiles case always cancelled failure success'.split())


def expression(source,line):
    tokens=[];position=0
    for match in TOKEN.finditer(source):
        if match.start()!=position:raise ValueError('Unsupported Actions expression token')
        position=match.end()
        if not match[0].isspace():tokens.append((match[0],line+source.count('\n',0,match.start())))
    if position!=len(source):raise ValueError('Unsupported Actions expression syntax')
    index=0;branches=[]
    def take(value=None):
        nonlocal index
        if index>=len(tokens) or value is not None and tokens[index][0]!=value:raise ValueError('Incomplete Actions expression')
        token=tokens[index];index+=1;return token
    def parse(minimum=0,depth=0):
        nonlocal index
        if depth>64:raise ValueError('Actions expression nesting exceeds analysis budget')
        token,at=take()
        if token=='!':parse(5,depth+1)
        elif token=='(':parse(0,depth+1);take(')')
        elif token.startswith("'") or re.fullmatch(r'[+-]?(?:\d[\w.]*|\.\d+)(?:[eE][+-]?\d+)?',token):pass
        elif re.fullmatch(r'[A-Za-z_][\w-]*',token):
            if index<len(tokens) and tokens[index][0]=='(':
                if token.lower() not in FUNCTIONS:raise ValueError('Unrecognized Actions expression function')
                take('(');arguments=0
                if index<len(tokens) and tokens[index][0]!=')':
                    while True:
                        parse(0,depth+1);arguments+=1
                        if index>=len(tokens) or tokens[index][0]!=',':break
                        take(',')
                take(')')
                if token.lower()=='case':
                    if arguments<3 or arguments%2!=1:raise ValueError('Invalid Actions case arguments')
                    branches.append(BranchEvidence('actions-case',at,(arguments-1)//2))
        else:raise ValueError('Invalid Actions expression operand')
        while index<len(tokens):
            operator=tokens[index][0]
            if operator=='.':
                take('.')
                member,_=take()
                if member!='*' and not re.fullmatch(r'[A-Za-z_][\w-]*',member):raise ValueError('Invalid Actions property reference')
            elif operator=='[':take('[');parse(0,depth+1);take(']')
            elif operator in PRECEDENCE and PRECEDENCE[operator]>=minimum:
                _,at=take();parse(PRECEDENCE[operator]+1,depth+1)
                if operator in {'&&','||'}:branches.append(BranchEvidence('actions-short-circuit',at))
            else:break
    parse()
    if index!=len(tokens):raise ValueError('Unsupported Actions expression suffix')
    return branches


def expression_spans(source):
    position=0
    while (start:=source.find('${{',position))>=0:
        cursor=start+3;quoted=False
        while cursor<len(source):
            if source[cursor]=="'":
                if quoted and source[cursor:cursor+2]=="''":cursor+=2;continue
                quoted=not quoted
            elif not quoted and source.startswith('}}',cursor):break
            cursor+=1
        if cursor==len(source):raise ValueError('Unclosed Actions expression')
        yield start,cursor+2,source[start+3:cursor]
        position=cursor+2


def mask_expressions(source):
    masked=list(source)
    for start,end,_ in expression_spans(source):
        for index in range(start,end):
            if masked[index] not in '\r\n':masked[index]='x' if index==start else ' '
    return ''.join(masked)


def analyze_workflow(data,base,analyze):
    try:
        import yaml
        from yaml.nodes import MappingNode,SequenceNode,ScalarNode
        if version('PyYAML')!='6.0.3':raise ValueError('Workflow YAML parser differs from analysis contract')
        text=data.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n');root=yaml.compose(text,Loader=yaml.BaseLoader)
        def fields(node):
            if not isinstance(node,MappingNode):return {}
            if any(not isinstance(key,ScalarNode) for key,_ in node.value):raise ValueError('Unsupported workflow mapping key')
            return {key.value:(key,value) for key,value in node.value}
        def value(node,key):return fields(node).get(key,(None,None))[1]
        def scalar(node):return node.value if isinstance(node,ScalarNode) else None
        def source_text(node):
            if node.style!='>':return node.value
            lines=text.splitlines()[node.start_mark.line+1:node.end_mark.line]
            indent=min((len(line)-len(line.lstrip()) for line in lines if line.strip()),default=0)
            return '\n'.join(line[indent:] for line in lines)
        def expression_at(source,node,offset=0):
            first=node.start_mark.line+1+int(node.style in {'|','>'})
            result=expression(source,first+offset)
            if node.start_mark.line==node.end_mark.line:return [replace(branch,line=first) for branch in result]
            if result and node.style not in {'|','>'}:raise ValueError('Quoted multiline workflow expression needs source-preserving analysis')
            return result
        branches=[];structure=[];functions=[];pending=[(root,0)];seen=set();scalars=[];scored=set();conditions_seen=set();program_audits={};containers=max_depth=0
        while pending:
            node,depth=pending.pop()
            if node is None or id(node) in seen:continue
            seen.add(id(node))
            if len(seen)>100000:raise ValueError('Workflow node count exceeds analysis budget')
            if isinstance(node,ScalarNode):
                scalars.append(node)
                original=source_text(node)
                for start,_,source in expression_spans(original):branches.extend(expression_at(source,node,original.count('\n',0,start)))
                continue
            if isinstance(node,MappingNode):children=[child for pair in node.value for child in pair]
            elif isinstance(node,SequenceNode):children=node.value
            else:raise ValueError('Unsupported workflow YAML node')
            depth+=1;containers+=1;max_depth=max(max_depth,depth);line=node.start_mark.line+1
            if depth>3:structure.append(BranchEvidence('nesting-excess',line,depth-3))
            fanout=sum(isinstance(child,(MappingNode,SequenceNode)) for child in children)
            if fanout>8:structure.append(BranchEvidence('fanout-excess',line,fanout-8))
            pending.extend((child,depth) for child in reversed(children))
        def conditional(node):
            pair=fields(node).get('if')
            if pair:
                key,body=pair;source=scalar(body)
                if id(key) in conditions_seen:return
                conditions_seen.add(id(key))
                if source is None:raise ValueError('Workflow condition is not a scalar')
                branches.append(BranchEvidence('workflow-if',key.start_mark.line+1))
                scored.add(id(body))
                if '${{' not in source:branches.extend(expression_at(source_text(body),body))
        def defaults(node):return scalar(value(value(value(node,'defaults'),'run'),'shell'))
        def runner_shells(job,step):
            runner=value(job,'runs-on');labels=[];axis_variants=False
            if isinstance(runner,SequenceNode):labels=[scalar(node) for node in runner.value]
            elif scalar(runner):
                label=scalar(runner);matrix=re.fullmatch(r'\s*\$\{\{\s*matrix\.([\w-]+)\s*}}\s*',label)
                if matrix:
                    axis_variants=True
                    axis=value(value(value(job,'strategy'),'matrix'),matrix[1])
                    if isinstance(axis,SequenceNode):labels=[scalar(node) for node in axis.value]
                else:labels=[label]
            candidates=set()
            for label in labels:
                if label and re.search(r'windows',label,re.I):candidates.add('pwsh')
                elif label and re.search(r'ubuntu|macos|linux',label,re.I):candidates.add('bash')
                elif axis_variants:return []
            condition=scalar(value(step,'if')) or ''
            condition=condition.strip().removeprefix('${{').removesuffix('}}').strip()
            constraint=re.fullmatch(r"runner\.os\s*(==|!=)\s*'(Windows|Linux|macOS)'",condition)
            if constraint:
                expected='pwsh' if constraint[2]=='Windows' else 'bash'
                if constraint[1]=='==':candidates={expected}
                elif constraint[2]=='Windows':candidates.discard('pwsh')
            return sorted(candidates)
        default_shell=defaults(root);jobs=value(root,'jobs');jobs=list(fields(jobs).values())
        composite=value(root,'runs')
        if scalar(value(composite,'using'))=='composite':jobs.append((None,composite))
        for _,job in jobs:
            conditional(job);shell=defaults(job) or default_shell
            steps=value(job,'steps')
            if steps is None:continue
            if not isinstance(steps,SequenceNode):raise ValueError('Workflow steps must be a sequence')
            for step in steps.value:
                conditional(step);script=value(step,'run')
                if script is None:continue
                raw=scalar(script)
                if raw is None:raise ValueError('Workflow run source must be a scalar')
                scored.add(id(script))
                if any(re.fullmatch(r'\s*\$\{\{[\s\S]*}}\s*',line) for line in raw.splitlines()):raise ValueError('Computed workflow program needs its rendered source before scoring')
                selected=scalar(value(step,'shell')) or shell
                candidates=[selected] if selected else runner_shells(job,step)
                if not candidates:raise ValueError('Workflow runner needs an explicit shell for reliable analysis')
                source=mask_expressions(raw);parsed=None
                audit=lambda metric:([(f.symbol,[(b.kind,b.contribution) for b in f.branches]) for f in metric.functions],[(b.kind,b.contribution) for b in metric.unattributed_branches])
                for selected in candidates:
                    command=selected.split()[0].lower()
                    language={'bash':'bash','sh':'bash','pwsh':'powershell','powershell':'powershell','cmd':'batch','python':'python','python3':'python','node':'javascript'}.get(command)
                    if not language:raise ValueError('Workflow shell language is not supported')
                    candidate=analyze(source.encode(),relative_path=base['path'],language=language)
                    if candidate.parse_error or parsed and audit(candidate)!=audit(parsed):raise ValueError('Workflow scripts differ across default runner shells; an explicit shell is required')
                    if parsed is None:parsed=candidate;parsed_language=language
                language=parsed_language
                if parsed.parse_error:raise ValueError('Workflow script syntax is not fully recognized')
                first=script.start_mark.line+1+int(script.style in {'|','>'})
                choices=bool(parsed.unattributed_branches) or any(f.cyclomatic>1 for f in parsed.functions)
                if script.style=='>' and choices:
                    lines=text.splitlines()[script.start_mark.line+1:script.end_mark.line]
                    indent=min((len(line)-len(line.lstrip()) for line in lines if line.strip()),default=0)
                    unfolded=mask_expressions('\n'.join(line[indent:] for line in lines))
                    mapped=analyze(unfolded.encode(),relative_path=base['path'],language=language)
                    if mapped.parse_error or audit(mapped)!=audit(parsed):raise ValueError('Folded workflow script needs a source-preserving analysis')
                    parsed=mapped
                inline=script.start_mark.line==script.end_mark.line
                if not inline and script.style not in {'|','>'} and choices:raise ValueError('Quoted multiline workflow script needs a source-preserving analysis')
                def at(line):return first if inline else min(base['lines'],first+line-1)
                signature=audit(parsed)
                if id(script) in program_audits:
                    if program_audits[id(script)]!=signature:raise ValueError('Shared workflow source has different control flow in its declared shells')
                    continue
                program_audits[id(script)]=signature
                for f in parsed.functions:
                    functions.append(replace(f,symbol=f'<run:{first}>/{f.symbol}',line=at(f.line),end_line=at(f.end_line),
                        branches=tuple(replace(b,line=at(b.line)) for b in f.branches)))
                if parsed.unattributed_branches:
                    extra=tuple(replace(b,line=at(b.line)) for b in parsed.unattributed_branches)
                    functions.append(FunctionMetric(f'<run:{first}>/<module>',1,first,min(base['lines'],script.end_mark.line+1),1+sum(b.contribution for b in extra),extra))
        if branches:functions.append(FunctionMetric('<workflow>',1,1,max(1,base['lines']),1+sum(b.contribution for b in branches),tuple(branches)))
        structural={'containers':containers,'max_depth':max_depth,'nesting_points':sum(b.contribution for b in structure if b.kind=='nesting-excess'),'fanout_points':sum(b.contribution for b in structure if b.kind=='fanout-excess')}
        structural['unscored_source_sha256']=hashlib.sha256(json.dumps([(node.tag,node.value) for node in scalars if id(node) not in scored],separators=(',',':')).encode()).hexdigest()
        if functions:return FileMetric(**(base|{'metric_family':'control_flow'}),functions=tuple(functions),structural=structural,structure_branches=tuple(structure))
        return FileMetric(**base,functions=(FunctionMetric('<document>',1,1,max(1,base['lines']),1+sum(b.contribution for b in structure),tuple(structure)),),structural=structural)
    except Exception as exc:return FileMetric(**base,parse_error=f'Workflow analysis unavailable: {type(exc).__name__}: {exc}' if isinstance(exc,ValueError) else f'Workflow analysis unavailable: {type(exc).__name__}')
