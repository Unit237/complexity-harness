"""NSIS command syntax and explicit source decisions; never invoke makensis."""
import re
from .models import BranchEvidence,FileMetric,FunctionMetric

TOKENS=re.compile(r'\s+|(?:;|#)[^\n]*|/\*[\s\S]*?\*/|"(?:\$\\.|[^"\n])*"|\x27(?:\$\\.|[^\x27\n])*\x27|`(?:\$\\.|[^`\n])*`|[^\s"\x27`;#]+')
CHOICES={'iferrors':1,'ifabort':1,'iffileexists':1,'ifRebootFlag':1,'ifsilent':1,'strCmp':1,'strCmpS':1,'intcmp':2,'intcmpu':2,'int64cmp':2}
CHOICES={key.lower():value for key,value in CHOICES.items()}


def analyze_installer(data,base):
    try:
        text=data.decode('utf-8-sig');units=[];owner=None;blocks=[];parents=[];preprocessor=[]
        for line,source in enumerate(text.splitlines(),1):
            tokens=[];offset=0
            for match in TOKENS.finditer(source):
                if match.start()!=offset:raise ValueError('Invalid NSIS quoting')
                offset=match.end();value=match.group()
                if not value.isspace() and not value.startswith((';','#','/*')):tokens.append(value)
            if offset!=len(source):raise ValueError('Invalid NSIS token')
            if not tokens:continue
            command=tokens[0].lower();choice=CHOICES.get(command,0)
            if command in {'function','section','!macro'}:
                if len(tokens)<2:raise ValueError('Missing NSIS block name')
                parents.append(owner);owner={'symbol':tokens[1],'line':line,'end':line,'branches':[]};units.append(owner);blocks.append(command)
            elif command in {'functionend','sectionend','!macroend'}:
                expected={'functionend':'function','sectionend':'section','!macroend':'!macro'}[command]
                if not blocks or blocks.pop()!=expected:raise ValueError('Unbalanced NSIS block')
                owner['end']=line;owner=parents.pop();continue
            elif command in {'!if','!ifdef','!ifndef','!ifmacrodef','!ifmacrondef'}:preprocessor.append(command);choice=1
            elif command=='!else':
                if not preprocessor:raise ValueError('Unmatched NSIS alternative')
                choice=int(len(tokens)>1)
            elif command=='!endif':
                if not preprocessor:raise ValueError('Unmatched NSIS endif')
                preprocessor.pop()
            elif command in {'${if}','${ifnot}','${unless}','${elseif}','${andif}','${orif}','${for}','${foreach}','${dowhile}','${dountil}','${loopwhile}','${loopuntil}'}:choice=1
            elif command=='messagebox':
                choice=max(0,len(re.findall(r'\bID(?:ABORT|CANCEL|CONTINUE|IGNORE|NO|OK|RETRY|TRYAGAIN|YES)\b',' '.join(tokens[3:])))-1)
            if owner is None and choice:
                owner={'symbol':'<installer>','line':line,'end':line,'branches':[]};units.append(owner)
            if owner:
                owner['end']=line
                if choice:owner['branches'].append(BranchEvidence('nsis-'+command,line,choice))
        if blocks or preprocessor:raise ValueError('Unclosed NSIS block')
        return FileMetric(**base,functions=tuple(FunctionMetric(u['symbol'],i+1,u['line'],u['end'],1+sum(b.contribution for b in u['branches']),tuple(u['branches'])) for i,u in enumerate(units)))
    except (ValueError,UnicodeDecodeError) as exc:return FileMetric(**base,parse_error=str(exc))
