"""Read Go template actions as data, retaining decisions and physical lines.

Actions are tokenized with Go quoting rules. Blocks are balanced; strings and
comments cannot manufacture branches. No template functions are invoked.
"""
import re
import hashlib
from .models import BranchEvidence, FileMetric, FunctionMetric

TOKEN = re.compile(r'\s+|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|`[^`]*`|:=|[()|,=]|[^\s()|,=:"\x27`]+')


def actions(text):
    position=0
    while (start:=text.find('{{',position))>=0:
        cursor=start+2; quote=None; comment=False
        while cursor<len(text):
            if comment:
                end=text.find('*/',cursor)
                if end<0:raise ValueError('Unclosed template comment')
                cursor=end+2;comment=False;continue
            char=text[cursor]
            if quote:
                if char=='\\' and quote!='`':cursor+=2;continue
                if char==quote:quote=None
            elif text.startswith('/*',cursor):comment=True;cursor+=2;continue
            elif char in '\"\x27`':quote=char
            elif text.startswith('}}',cursor):break
            cursor+=1
        if cursor>=len(text):raise ValueError('Unclosed template action')
        raw=text[start+2:cursor].strip().removeprefix('-').removesuffix('-').strip()
        tokens=[];offset=0
        for match in TOKEN.finditer(raw):
            if match.start()!=offset:raise ValueError('Invalid template token')
            offset=match.end();value=match.group()
            if not value.isspace() and not value.startswith('/*'):tokens.append(value)
        if offset!=len(raw):raise ValueError('Invalid template quoting')
        if tokens and tokens[0] not in {'<','%'}:
            for token in tokens:
                if token[:1] in {'"',"'",'`'} or token in {'(',')','|',',','=',':='}:continue
                if not re.fullmatch(r'(?:[A-Za-z_][\w.]*|\$(?:[\w.]+)?|\.[\w.]*|[+-]?(?:\d[\w.]*|\.\d+))',token):raise ValueError('Unsupported template expression token')
            if tokens[-1] in {'|',':=','='}:raise ValueError('Incomplete template pipeline')
        depth=0
        for token in tokens:
            depth+=(token=='(')-(token==')')
            if depth<0:raise ValueError('Unbalanced template expression')
        if depth:raise ValueError('Unbalanced template expression')
        yield start,cursor+2,tokens
        position=cursor+2


def template_parts(data, base):
    text=data.decode('utf-8-sig');masked=list(text);blocks=[];units=[]
    current={'symbol':'<template>','line':1,'end_line':max(1,base['lines']),'branches':[]}
    units.append(current);parents=[];count=0
    for start,end,tokens in actions(text):
        count+=1;line=text.count('\n',0,start)+1
        # Host grammars see a stable placeholder, not rendered customer code.
        line_start=text.rfind('\n',0,start)+1
        line_end=text.find('\n',end)
        line_end=len(text) if line_end<0 else line_end
        standalone=not (text[line_start:start].strip() or text[end:line_end].strip())
        replacement='x' if not standalone and tokens and tokens[0] not in {'if','range','with','else','end','define','block','/*'} else ' '
        adjacent_identifier=replacement=='x' and ((start>0 and (text[start-1].isalnum() or text[start-1]=='_')) or (end<len(text) and (text[end].isalnum() or text[end]=='_')))
        for index in range(start,end):
            if masked[index] not in '\r\n':masked[index]=replacement if index==start or adjacent_identifier else ' '
        if not tokens:continue
        command=tokens[0]
        if command in {'if','range','with','define','block'}:
            if len(tokens)<2:raise ValueError('Missing template block expression')
            blocks.append(command)
            if command in {'define','block'}:
                if tokens[1][:1] not in {'"','`'}:raise ValueError('Template name must be quoted')
                parents.append(current)
                current={'symbol':tokens[1][1:-1],'line':line,'end_line':line,'branches':[]};units.append(current)
            else:current['branches'].append(BranchEvidence('template-'+command,line))
        elif command=='end':
            if len(tokens)!=1 or not blocks:raise ValueError('Unmatched template end')
            if blocks.pop() in {'define','block'}:
                current['end_line']=line;current=parents.pop()
        elif command=='else':
            if not blocks or blocks[-1] not in {'if','range','with'}:raise ValueError('Unmatched template else')
            if len(tokens)>1:
                if tokens[1] not in {'if','with'}:raise ValueError('Unsupported template alternative')
                current['branches'].append(BranchEvidence('template-else-'+tokens[1],line))
        elif command in {'break','continue'} and 'range' not in blocks:
            raise ValueError('Template loop control outside range')
        # and/or are Go template short-circuit functions. Every subsequent
        # operand adds a choice; count only calls, never quoted text/fields.
        for index,token in enumerate(tokens):
            if token not in {'and','or'}:continue
            depth=0;operands=int(index>0 and tokens[index-1]=='|')
            for operand in tokens[index+1:]:
                if depth==0 and operand in {')','|'}:break
                if depth==0 and operand not in {',','='}:operands+=1
                depth+=(operand=='(')-(operand==')')
            if operands<1:raise ValueError('Short-circuit function needs operands')
            if operands>1:current['branches'].append(BranchEvidence('template-short-circuit',line,operands-1))
    if blocks:raise ValueError('Unclosed template block')
    functions=tuple(FunctionMetric(u['symbol'],index+1,u['line'],u['end_line'],
        1+sum(b.contribution for b in u['branches']),tuple(u['branches'])) for index,u in enumerate(units)
        if u['branches'] or u['symbol']!='<template>')
    return ''.join(masked).encode(),functions,count


def analyze_template(data,base,analyze):
    try:
        masked,functions,count=template_parts(data,base)
        if not count and data.strip():raise ValueError('Template dialect is not identified')
        from pathlib import PurePosixPath
        host=PurePosixPath(base['path']).stem
        language=next((language for extension,language in {'.go':'go','.py':'python','.js':'javascript','.ts':'typescript','.html':'html'}.items() if host.endswith(extension)),None)
        if language:
            prefix=b'package template\n' if language=='go' and not re.search(rb'(?m)^\s*package\b',masked) else b''
            if language=='go':
                # A template parameter-list hole has unknown arity, but Go has
                # no default-parameter decisions to hide in that hole.
                masked=re.sub(rb'(func\b[^\n{]*\([^\n)]*?)\bx(?=\s*\))',rb'\1x interface{}',masked)
            measured=analyze(prefix+masked,relative_path=base['path'],language=language)
            if measured.parse_error:raise ValueError('Template host language could not be fully analyzed')
            offset=1 if prefix else 0
            from dataclasses import replace
            functions+=tuple(replace(f,line=max(1,f.line-offset),end_line=max(1,f.end_line-offset),
                branches=tuple(replace(b,line=max(1,b.line-offset)) for b in f.branches)) for f in measured.functions if measured.metric_family=='control_flow')
        elif re.search(rb'(?m)^\s*(?:func|def|class|function)\b',masked):
            raise ValueError('Template host language must be identified before scoring')
        literal=[];position=0
        if not language:
            text=data.decode('utf-8-sig')
            for start,end,tokens in actions(text):
                literal.append(text[position:start]);literal.extend(token for token in tokens if token[:1] in {'"',"'",'`'});position=end
            literal.append(text[position:])
        return FileMetric(**base,functions=functions,structural={} if language else {
            'unscored_source_sha256':hashlib.sha256(''.join(literal).encode()).hexdigest()})
    except (ValueError,UnicodeDecodeError) as exc:
        return FileMetric(**base,parse_error=str(exc))
