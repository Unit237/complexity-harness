"""Static GNU Make syntax with shell recipes and make-function decisions."""
from dataclasses import replace
import re
from .models import BranchEvidence,FileMetric,FunctionMetric


def make_expressions(source,line,branches,analyze,path,functions,macros=frozenset()):
    """Mask expansions for the shell while separately measuring their source."""
    pieces=[];index=0
    while index<len(source):
        if source[index:index+2]=='$$':pieces.append('$');index+=2;continue
        if source[index]=='$' and index+1<len(source) and source[index+1] not in '({':pieces.append('x');index+=2;continue
        if source[index:index+2] not in {'$(','${'}:pieces.append(source[index]);index+=1;continue
        end=index+2;closing=')' if source[index+1]=='(' else '}';depth=1
        while end<len(source) and depth:
            if source[end]==source[index+1]:depth+=1
            elif source[end]==closing:depth-=1
            if depth>100:raise ValueError('Make expansion nesting exceeds the analysis budget')
            end+=1
        if depth:raise ValueError('Unclosed Make expansion')
        body=source[index+2:end-1];name,*rest=body.split(None,1)
        expression_line=line+source.count('\n',0,index)
        value=rest[0] if rest else ''
        if name=='eval' and not re.match(r'^\w+\s*(?::=|=)',value):
            call=re.match(r'^\$\(call\s+([\w-]+)(?:,|\))',value)
            if not call or call[1] not in macros:raise ValueError('Dynamic Make eval requires expanded-source analysis')
        replacement='' if name=='eval' else 'x'
        if name in {'if','foreach','or','and'}:
            contribution=1
            if name in {'or','and'}:
                depth=0;commas=0
                for char in value:
                    depth+=(char=='(')-(char==')')
                    commas+=char==',' and depth==0
                contribution=commas
            if contribution:branches.append(BranchEvidence('make-'+name,expression_line,contribution))
        if name=='shell':
            shell=make_expressions(value,expression_line,branches,analyze,path,functions,macros)
            measured=analyze(shell.encode(),relative_path=path,language='bash')
            if measured.parse_error:raise ValueError('Make shell function syntax is not fully recognized')
            functions.extend(offset(f,expression_line,'shell') for f in measured.functions)
        elif rest:
            make_expressions(value,expression_line,branches,analyze,path,functions,macros)
        pieces.append(replacement+'\n'*source[index:end].count('\n'));index=end
    return ''.join(pieces)


def offset(function,line,symbol):
    return replace(function,symbol=f'<make:{symbol}:{line}>/{function.symbol}',line=function.line+line-1,
        end_line=function.end_line+line-1,branches=tuple(replace(b,line=b.line+line-1) for b in function.branches))


def analyze_make(data,base,analyze):
    lines=data.decode('utf-8-sig').splitlines();index=0;depth=0;branches=[];functions=[];containers=0
    macros=set(re.findall(r'(?m)^(?:override\s+)?define\s+([\w-]+)',data.decode('utf-8-sig')))
    try:
        while index<len(lines):
            raw=lines[index];line=index+1;index+=1
            source=raw
            while source.endswith('\\') and index<len(lines):source=source+'\n'+lines[index];index+=1
            stripped=source.strip()
            if not stripped or stripped.startswith('#'):continue
            if raw.startswith('\t') and not re.match(r'^(?:if(?:eq|neq|def|ndef)|else(?:\s+if\w+)?|endif)\b',stripped):
                shell=make_expressions(source.lstrip('\t').lstrip('@-+'),line,branches,analyze,base['path'],functions,macros)
                measured=analyze(shell.encode(),relative_path=base['path'],language='bash')
                if measured.parse_error:raise ValueError('Make recipe syntax is not fully recognized')
                functions.extend(offset(f,line,'recipe') for f in measured.functions);continue
            conditional=re.match(r'(?:(else)\s+)?(ifeq|ifneq|ifdef|ifndef)\b',stripped)
            if conditional:
                if conditional[1] and not depth:raise ValueError('Unmatched Make alternative')
                if not conditional[1]:depth+=1
                branches.append(BranchEvidence('make-'+conditional[2],line));containers+=1
            elif stripped=='endif':
                depth-=1
                if depth<0:raise ValueError('Unmatched Make endif')
            elif stripped=='else':
                if not depth:raise ValueError('Unmatched Make else')
            elif re.match(r'^(?:override\s+|export\s+|private\s+)*(?:[^:=\s]+|\$\([^\n]*\))\s*(?::=|::=|\?=|\+=|!=|=)',stripped):
                make_expressions(stripped,line,branches,analyze,base['path'],functions,macros)
            elif re.match(r'^(?:-?include|sinclude|export|unexport|vpath)\b',stripped):
                make_expressions(stripped,line,branches,analyze,base['path'],functions,macros)
            elif re.match(r'^(?:override\s+)?define\b',stripped):
                body=[];nesting=1
                while index<len(lines):
                    current=lines[index];index+=1
                    if re.match(r'^(?:override\s+)?define\b',current):nesting+=1
                    elif current.strip()=='endef':nesting-=1
                    if not nesting:break
                    body.append(current)
                if nesting:raise ValueError('Unclosed Make definition')
                source='\n'.join(body);nested=analyze_make(source.encode(),base|{'lines':len(body)},analyze)
                if nested.parse_error:
                    nested=analyze(make_expressions(source,line+1,branches,analyze,base['path'],functions,macros).encode(),relative_path=base['path'],language='bash')
                if nested.parse_error:raise ValueError('Make definition body is not fully recognized')
                if nested.metric_family=='control_flow':functions.extend(offset(f,line+1,'define') for f in nested.functions)
            elif ':' in stripped:
                containers+=1
                make_expressions(stripped,line,branches,analyze,base['path'],functions,macros)
            elif stripped.startswith('$('):
                make_expressions(stripped,line,branches,analyze,base['path'],functions,macros)
            else:raise ValueError('Unrecognized Make statement')
        if depth:raise ValueError('Unclosed Make conditional')
        if branches:functions.append(FunctionMetric('<make>',1,1,max(1,base['lines']),1+sum(b.contribution for b in branches),tuple(branches)))
        if functions:return FileMetric(**(base|{'metric_family':'control_flow'}),functions=tuple(functions),structural={'containers':containers,'max_depth':1})
        return FileMetric(**base,functions=(FunctionMetric('<document>',1,1,max(1,base['lines']),1,()),),structural={'containers':containers,'max_depth':1,'nesting_points':0,'fanout_points':0})
    except (ValueError,IndexError,RecursionError) as exc:
        return FileMetric(**base,parse_error=str(exc))
