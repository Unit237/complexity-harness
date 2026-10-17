"""Generate static Go/Plan 9 vocabulary from a pinned Go SDK, never customer code."""
import hashlib
import json
from pathlib import Path
import re
import subprocess


def generate(sdk):
    if subprocess.check_output([str(sdk/'bin/go'),'version'],text=True).split()[2]!='go1.25.3':
        raise ValueError('Use Go 1.25.3 for this versioned vocabulary')
    source=sdk/'src/cmd'
    arch=(source/'asm/internal/arch/arch.go').read_text()
    inputs={};names={};jumps={}
    def read(path):
        inputs[str(path.relative_to(source))]=hashlib.sha256(path.read_bytes()).hexdigest()
        return path.read_text()
    def words(text):return re.findall(r'"([A-Za-z][A-Za-z0-9]*)"',text)
    common=set(words(read(source/'internal/obj/util.go').split('var Anames = []string{',1)[1].split('\n}',1)[0]))
    read(source/'asm/internal/arch/arch.go')
    profiles={'x86':('X86','X86'),'arm':('Arm','Arm'),'arm64':('Arm64','Arm64'),'ppc64':('PPC64','PPC64'),
              'mips':('Mips','MIPS'),'loong64':('Loong64','Loong64'),'riscv':('RISCV64','RISCV'),
              's390x':('S390x','S390x'),'wasm':('Wasm','Wasm')}
    for profile,(builder,jumper) in profiles.items():
        vocabulary=set(words(read(source/f'internal/obj/{profile}/anames.go')))|common
        body=re.search(r'^func arch'+builder+r'\([^\n]*\{([\s\S]*?)^}',arch,re.M)[1]
        vocabulary.update(re.findall(r'instructions\["(\w+)"\]',body))
        if profile=='x86':
            branches={word for word in vocabulary if word.startswith(('J','LOOP')) or word=='XBEGIN'}
            unconditional={'JMP','CALL'}
        else:
            helper=arch if profile in {'riscv','wasm'} else read(source/f'asm/internal/arch/{profile}.go')
            if profile in {'arm','arm64'}:
                block=re.search(r'var '+profile+r'Jump = map\[string\]bool\{([\s\S]*?)\n}',helper)[1]
            else:block=re.search(r'func jump'+jumper+r'\([^\n]*\{([\s\S]*?)^}',helper,re.M)[1]
            branches=set(words(block))
            unconditional={
                'arm':{'B','BL','BX','BLX','JMP','CALL'},'arm64':{'B','BL','JMP','CALL','ADR','ADRP'},
                'ppc64':{'BL','BR','CALL','JMP'},'mips':{'JAL','JALR','JR','JMP','CALL'},
                'loong64':{'JIRL','JAL','JMP','CALL'},'riscv':{'JAL','JALR','JMP','CALL'},
                's390x':{'BR','CALL','JMP'},'wasm':{'JMP','CALL','Call','Br'},
            }[profile]
        # Conditional select/move/set instructions encode a source choice too.
        branches.update(word for word in vocabulary if re.match(r'^(?:CMOV|CSEL|CSINC|CSINV|CSNEG|CSET|LOC|SEL)',word))
        if profile=='x86':branches.update(word for word in vocabulary if re.fullmatch(r'SET(?:EQ|NE|CS|CC|HI|LS|GE|LT|GT|LE|MI|PL|PS|PC|OS|OC)',word))
        if profile=='wasm':branches.update({'If','BrIf','BrTable','Select'})
        vocabulary.update(branches)
        names[profile]=sorted(vocabulary);jumps[profile]=sorted(branches-unconditional)
    return {'source':'https://github.com/golang/go/tree/go1.25.3/src/cmd','source_sha256':dict(sorted(inputs.items())),
            'architectures':names,'conditional_instructions':jumps}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sdk',type=Path)
    args=parser.parse_args()
    output=Path(__file__).parents[1]/'src/complexity_harness/vendor/go-assembly-opcodes.json'
    output.write_text(json.dumps(generate(args.sdk),indent=2)+'\n')
