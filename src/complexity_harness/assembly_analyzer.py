"""Static Plan 9/Go assembly reader. Includes are never opened or executed.

Instruction vocabulary is pinned to Go 1.25.3. Functions and macro definitions
own their explicit choices once; this measures source, not expanded binaries.
Unknown dialects/opcodes fail closed instead of becoming zero-decision code.
"""
import json
import hashlib
from pathlib import Path
import re
from .models import BranchEvidence, FileMetric, FunctionMetric

VOCABULARY=json.loads((Path(__file__).parent/'vendor/go-assembly-opcodes.json').read_text())
COMMON_OPCODES=set('TEXT DATA GLOBL PCDATA FUNCDATA PCALIGN END RET CALL JMP NOP UNDEF WORD LONG QUAD BYTE'.split())
OPCODES=set().union(*VOCABULARY['architectures'].values()) | COMMON_OPCODES
CONDITIONS=set('EQ NE CS CC MI PL VS VC HI LS GE LT GT LE HS LO'.split())

def architecture(path):
    aliases={'amd64':'x86','386':'x86','ppc64le':'ppc64','ppc64x':'ppc64','mips64':'mips','mips64le':'mips','mipsle':'mips','mips64x':'mips','mipsx':'mips','riscv64':'riscv'}
    matches=re.findall(r'(?:^|[_/.\-])(amd64|386|arm64|arm|ppc64le|ppc64x|ppc64|mips64le|mips64x|mips64|mipsle|mipsx|mips|riscv64|loong64|s390x|wasm)(?=[_/.\-]|$)',path)
    return aliases.get(matches[-1],matches[-1]) if matches else None

def conditional(opcode,profile):
    profiles=[profile] if profile else [key for key,words in VOCABULARY['architectures'].items() if opcode in words]
    choices={opcode in VOCABULARY['conditional_instructions'][key] for key in profiles}
    if len(choices)>1:raise ValueError('Ambiguous assembly architecture; an architecture filename is needed')
    return True in choices


def without_comments(text):
    token=re.compile(r'"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|//[^\n]*|/\*[\s\S]*?\*/')
    return token.sub(lambda m: re.sub(r'[^\r\n]',' ',m.group()) if m.group().startswith(('//','/*')) else m.group(),text)


def analyze_assembly(data,base):
    try:
        text=without_comments(data.decode('utf-8-sig'))
        if not text.strip():return FileMetric(**base)
        if '/*' in text:raise ValueError('Unclosed assembly comment')
        if not re.search(r'(?m)^\s*(?:TEXT\b|#\s*(?:include|define)\b)',text):
            raise ValueError('Assembly dialect is not Plan 9/Go')
        units=[];owner=None;macro=None;conditional_depth=0
        profile=architecture(base['path'])
        macro_names=set(re.findall(r'(?m)^\s*#\s*define\s+(\w+)',text))
        macro_parameters=set()
        def new_unit(name,line):
            unit={'name':name,'line':line,'end':line,'branches':[]};units.append(unit);return unit
        for line,raw in enumerate(text.splitlines(),1):
            source=raw.strip();continuation=source.endswith('\\');source=source.removesuffix('\\').rstrip()
            if not source:
                if not continuation:macro=None
                continue
            directive=re.match(r'#\s*(\w+)\s*(.*)',source)
            target=macro or owner
            if directive:
                kind,body=directive.groups()
                if kind in {'if','ifdef','ifndef','elif'}:
                    if kind!='elif':conditional_depth+=1
                    elif not conditional_depth:raise ValueError('Unmatched assembly elif')
                    target=target or new_unit('<preprocessor>',line)
                    target['branches'].append(BranchEvidence('assembly-preprocessor',line))
                    for _ in re.finditer(r'&&|\|\|',body):target['branches'].append(BranchEvidence('short-circuit',line))
                elif kind=='endif':
                    conditional_depth-=1
                    if conditional_depth<0:raise ValueError('Unmatched assembly endif')
                elif kind=='define':
                    definition=re.match(r'(\w+)(\([^)]*\))?\s*(.*)',body)
                    if not definition:raise ValueError('Invalid assembly macro')
                    name,parameters,source=definition.groups()
                    if re.search(r'\b(?:if|for|while|case|catch)\b|\?|&&|\|\|',source):raise ValueError('Macro body is not assembly syntax')
                    if parameters and re.match(r'^[0-9$()~+*/|&<> -]+(?:\w+\))?$',source):continue
                    if parameters or continuation or source.split(' ',1)[0] in (set(VOCABULARY['architectures'][profile])|COMMON_OPCODES if profile else OPCODES):
                        macro=new_unit('<macro:'+name+'>',line);target=macro
                        macro_parameters=set(re.findall(r'\w+',parameters or ''))
                    else:continue  # Scalar aliases cannot introduce instructions.
                elif kind not in {'include','undef','else','error','line','pragma'}:
                    raise ValueError('Unknown assembly directive')
                if kind!='define':continue
            if target:target['end']=line
            for statement in source.split(';'):
                statement=re.sub(r'^\s*[\w·<>]+:\s*','',statement).strip()
                if not statement:continue
                match=re.match(r'([\w.]+)(?:\s+|\(|$)',statement)
                if not match:raise ValueError('Unrecognized assembly statement')
                mnemonic=match[1];opcode=mnemonic.split('.')[0]
                if opcode=='TEXT':
                    symbol=re.match(r'TEXT\s+([^,]+)',statement)
                    if not symbol:raise ValueError('Missing assembly function symbol')
                    owner=new_unit(symbol[1],line);target=owner
                elif opcode not in OPCODES and opcode not in macro_names | macro_parameters and not re.match(r'\w+\s*\(',statement):
                    raise ValueError('Unknown assembly opcode or macro: '+opcode)
                elif profile and opcode in OPCODES-COMMON_OPCODES and opcode not in VOCABULARY['architectures'][profile] and opcode not in macro_names|macro_parameters:
                    raise ValueError('Assembly instruction does not match the declared architecture: '+opcode)
                if opcode in OPCODES and opcode not in macro_names and (conditional(opcode,profile) or set(mnemonic.split('.')[1:]) & CONDITIONS):
                    target=target or new_unit('<module>',line)
                    target['branches'].append(BranchEvidence('assembly-conditional',line))
                if target:target['end']=line
            if not continuation:macro=None;macro_parameters=set()
        if conditional_depth:raise ValueError('Unclosed assembly conditional')
        metrics=tuple(FunctionMetric(u['name'],i+1,u['line'],u['end'],1+sum(b.contribution for b in u['branches']),tuple(u['branches'])) for i,u in enumerate(units))
        return FileMetric(**base,functions=metrics,structural={'unscored_source_sha256':hashlib.sha256((profile or 'unspecified').encode()).hexdigest()})
    except (ValueError,UnicodeDecodeError) as exc:
        return FileMetric(**base,parse_error=str(exc))
