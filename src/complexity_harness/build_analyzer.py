"""Docker instructions retain shell control flow, including modern flags."""
from dataclasses import replace
import json
import re
from .models import FileMetric,FunctionMetric

INSTRUCTIONS=set('ADD ARG CMD COPY ENTRYPOINT ENV EXPOSE FROM HEALTHCHECK LABEL MAINTAINER ONBUILD RUN SHELL STOPSIGNAL USER VOLUME WORKDIR'.split())


def analyze_docker(data,base,analyze):
    text=data.decode('utf-8-sig');lines=text.splitlines();functions=[];index=0;containers=0
    shell='bash'
    try:
        while index<len(lines):
            source=lines[index].strip();line=index+1;index+=1
            if not source or source.startswith('#'):continue
            if source=='...':raise ValueError('Invalid source: elided Dockerfile excerpt (...) is not executable source')
            while source.splitlines()[-1].endswith('\\') and index<len(lines):
                source=source+'\n'+lines[index];index+=1
            match=re.match(r'([A-Za-z]+)\s+(.*)',source,re.S)
            if source.upper() in INSTRUCTIONS:raise ValueError('Invalid source: Docker instruction is missing its required arguments')
            if not match or match[1].upper() not in INSTRUCTIONS:raise ValueError('Unknown or incomplete Docker instruction')
            kind,body=match[1].upper(),match[2].strip();containers+=1
            if kind=='ONBUILD':
                nested=analyze_docker(body.encode(),base|{'lines':max(1,len(body.splitlines()))},analyze)
                if nested.parse_error:raise ValueError(nested.parse_error)
                functions.extend(replace(f,line=f.line+line-1,end_line=f.end_line+line-1,
                    branches=tuple(replace(b,line=b.line+line-1) for b in f.branches)) for f in nested.functions)
            elif kind=='SHELL':
                argv=json.loads(body)
                if not isinstance(argv,list) or not argv or any(not isinstance(x,str) for x in argv):raise ValueError('Invalid Docker SHELL')
                shell='bash' if argv[0].split('/')[-1] in {'sh','bash','dash','ash','zsh'} else None
            elif kind in {'RUN','CMD','ENTRYPOINT','HEALTHCHECK'}:
                # Flags belong to the Docker instruction. The remaining source
                # belongs to the selected shell, even if it starts with '['.
                body=re.sub(r'^(?:--[\w-]+=(?:"[^"]*"|\S+)\s+)+','',body)
                if kind=='HEALTHCHECK':
                    if body=='NONE':continue
                    if not body.upper().startswith('CMD '):raise ValueError('Invalid HEALTHCHECK command')
                    body=body[4:]
                if body.startswith('['):
                    try:
                        argv=json.loads(body)
                        if not isinstance(argv,list) or any(not isinstance(x,str) for x in argv):raise ValueError('Invalid Docker exec form')
                        # Explicit shell -c arguments are executable source too.
                        if len(argv)>=3 and argv[0].split('/')[-1] in {'sh','bash','dash','ash'} and '-c' in argv[1:-1]:body=argv[argv.index('-c')+1]
                        else:continue
                    except json.JSONDecodeError:
                        pass  # '[' is also the POSIX test command in shell form.
                if not shell:raise ValueError('Docker shell language is not supported')
                heredoc=re.match(r'<<-?([\w]+)\s*$',body)
                if heredoc:
                    delimiter=heredoc[1];parts=[]
                    while index<len(lines) and lines[index].strip()!=delimiter:parts.append(lines[index]);index+=1
                    if index==len(lines):raise ValueError('Unclosed Docker heredoc')
                    index+=1;body='\n'.join(parts);line+=1
                measured=analyze(body.encode(),relative_path=base['path'],language=shell)
                if measured.parse_error:raise ValueError('Docker shell syntax is not fully recognized')
                for f in measured.functions:
                    functions.append(replace(f,symbol=f'<{kind}:{line}>/{f.symbol}',line=f.line+line-1,
                        end_line=min(base['lines'],f.end_line+line-1),branches=tuple(replace(b,line=b.line+line-1) for b in f.branches)))
        if functions:return FileMetric(**(base|{'metric_family':'control_flow'}),functions=tuple(functions),structural={'containers':containers,'max_depth':1})
        unit=FunctionMetric('<document>',1,1,max(1,base['lines']),1,())
        return FileMetric(**base,functions=(unit,),structural={'containers':containers,'max_depth':1,'nesting_points':0,'fanout_points':0})
    except (ValueError,TypeError) as exc:
        return FileMetric(**base,parse_error=str(exc))
