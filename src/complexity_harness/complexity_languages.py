"""Versioned file classification. Unknown extensions remain in the denominator.

No customer configuration can turn a parser into an executable hook. Grammars
are bundled dependencies; scanning never runs customer programs or downloads.
"""
from pathlib import PurePosixPath

LANGUAGE_EXTENSIONS = {
    'python': 'py pyw pyi', 'javascript': 'js jsx mjs cjs',
    'typescript': 'ts mts cts', 'tsx': 'tsx', 'c': 'c h',
    'cpp': 'cc cpp cxx c++ hh hpp hxx ipp tpp', 'csharp': 'cs',
    'java': 'java', 'go': 'go', 'rust': 'rs', 'ruby': 'rb rake gemspec',
    'php': 'php phtml', 'kotlin': 'kt kts', 'swift': 'swift', 'dart': 'dart',
    'bash': 'sh bash zsh', 'lua': 'lua', 'hcl': 'tf tfvars hcl',
    'sql': 'sql', 'css': 'css', 'json': 'json jsonc', 'yaml': 'yaml yml',
    'html': 'html htm', 'dockerfile': 'dockerfile', 'make': 'mk',
    'toml': 'toml', 'xml': 'xml xsl xslt xsd svg', 'graphql': 'graphql gql',
    # Recognized source without a validated complexity adapter is explicit.
    'vue': 'vue', 'svelte': 'svelte', 'astro': 'astro', 'notebook': 'ipynb',
    'scss': 'scss sass less', 'scala': 'scala sc', 'elixir': 'ex exs',
    'erlang': 'erl hrl', 'clojure': 'clj cljs cljc edn', 'haskell': 'hs lhs',
    'fsharp': 'fs fsx fsi', 'ocaml': 'ml mli', 'objective-c': 'm mm',
    'fortran': 'f f90 f95 f03 for', 'cobol': 'cob cbl cpy', 'abap': 'abap',
    'r': 'r rmd', 'julia': 'jl', 'perl': 'pl pm', 'powershell': 'ps1 psm1',
    'solidity': 'sol', 'zig': 'zig', 'nim': 'nim', 'groovy': 'groovy gradle',
    'apex': 'cls trigger', 'ada': 'adb ads', 'pascal': 'pas pp',
    'assembly': 's asm', 'verilog': 'v sv svh', 'vhdl': 'vhd vhdl',
    'protobuf': 'proto', 'bicep': 'bicep', 'nix': 'nix', 'cmake': 'cmake',
    'config': 'ini cfg conf properties env',
}
EXTENSIONS = {'.'+ext: language for language, exts in LANGUAGE_EXTENSIONS.items() for ext in exts.split()}
NAMES = {'Dockerfile':'dockerfile', 'Containerfile':'dockerfile', 'Makefile':'make',
         'GNUmakefile':'make', 'Rakefile':'ruby', 'Gemfile':'ruby', 'Vagrantfile':'ruby',
         'Podfile':'ruby', 'Brewfile':'ruby', 'CMakeLists.txt':'cmake', 'Jenkinsfile':'groovy'}
ASSETS = set('png jpg jpeg gif webp ico avif mp3 mp4 mov wav woff woff2 ttf otf pdf zip gz bz2 xz tar 7z jar class pyc so dylib dll exe a o bin db sqlite sqlite3 lock'.split())
DOCS = {'.md', '.rst', '.adoc', '.txt', '.csv', '.tsv'}
DATA_DIRECTORIES = {'artifacts','reports','test-results','fixtures','__fixtures__','__snapshots__'}
GENERATED_SUFFIXES = ('.g.dart','.freezed.dart','.pb.go','_pb2.py','_pb2_grpc.py','.g.cs','.designer.cs')
LOCKS = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'uv.lock', 'Cargo.lock', 'Gemfile.lock', 'composer.lock', 'pubspec.lock', 'go.sum'}


def classify_path(path):
    path = PurePosixPath(path)
    name, suffix = path.name, path.suffix.lower()
    if suffix in {'.json','.jsonl','.ndjson','.har','.sarif','.xml'} and (set(path.parts[:-1]) & DATA_DIRECTORIES or path.as_posix()=='.complexity/architectural-memory.json'):
        return {'kind':'data', 'language':None, 'reason':'Recorded report or fixture data; retained outside the source score'}
    if name in {'.DS_Store','Thumbs.db'}:
        return {'kind':'asset', 'language':None, 'reason':'Operating-system metadata'}
    if name.lower().endswith(GENERATED_SUFFIXES):
        return {'kind':'generated', 'language':None, 'reason':'Recognized generated source suffix'}
    if name in LOCKS or name.endswith('.min.js') or name.endswith('.min.css') or name.endswith('.map'):
        return {'kind':'generated', 'language':None, 'reason':'Generated or dependency lock file'}
    if name == '.env' or name.startswith('.env.') or suffix in {'.pem', '.key', '.p12', '.pfx'}:
        return {'kind':'opaque', 'language':'configuration', 'reason':'Sensitive configuration; metadata only'}
    language = NAMES.get(name) or ('dockerfile' if name.startswith('Dockerfile.') else None) or EXTENSIONS.get(suffix)
    if language:
        return {'kind':'source', 'language':language, 'reason':None}
    if suffix in DOCS or name.lower() in {'license', 'licence', 'notice', 'authors', '.gitignore', '.gitattributes', '.dockerignore'}:
        return {'kind':'documentation', 'language':None, 'reason':'Documentation or repository metadata'}
    if suffix.lstrip('.') in ASSETS:
        return {'kind':'asset', 'language':None, 'reason':'Binary or packaged asset'}
    return {'kind':'unknown', 'language':'unknown', 'reason':'Unrecognized file type; metadata only'}
