"""Versioned file classification. Unknown extensions remain in the denominator.

No customer configuration can turn a parser into an executable hook. Grammars
are bundled dependencies; scanning never runs customer programs or downloads.
"""
from pathlib import PurePosixPath

LANGUAGE_EXTENSIONS = {
    'python': 'py pyw pyi', 'javascript': 'js jsx mjs cjs',
    'typescript': 'ts mts cts', 'tsx': 'tsx', 'c': 'c', 'c_header': 'h',
    'cpp': 'cc cpp cxx c++ hh hpp hxx ipp tpp', 'csharp': 'cs',
    'java': 'java', 'go': 'go', 'rust': 'rs', 'ruby': 'rb rake gemspec ru builder yajl mab nokogiri rabl',
    'php': 'php phtml', 'kotlin': 'kt kts', 'swift': 'swift', 'dart': 'dart',
    'bash': 'sh bash zsh', 'lua': 'lua', 'hcl': 'tf tfvars hcl',
    'sql': 'sql ddl', 'css': 'css', 'json': 'json jsonc', 'yaml': 'yaml yml sublime-syntax',
    'html': 'html htm', 'dockerfile': 'dockerfile', 'make': 'mk',
    'toml': 'toml', 'xml': 'xml xsl xslt xsd svg plist xcworkspacedata xcsettings xcscheme storyboard xib xcprivacy entitlements manifest csproj props targets dotsettings dbml layout jmx', 'graphql': 'graphql gql',
    'openstep': 'pbxproj', 'properties': 'properties xcconfig',
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
    'config': 'ini cfg conf env cnf', 'gomod': 'mod work',
    'starlark': 'bzl bazel bzlmod', 'batch': 'bat cmd',
    'gotemplate': 'tpl tmpl gotmpl', 'nsis':'nsi nsh', 'abnf':'abnf',
}
EXTENSIONS = {'.'+ext: language for language, exts in LANGUAGE_EXTENSIONS.items() for ext in exts.split()}
NAMES = {'Dockerfile':'dockerfile', 'Containerfile':'dockerfile', 'Makefile':'make',
         'GNUmakefile':'make', 'Rakefile':'ruby', 'Gemfile':'ruby', 'Vagrantfile':'ruby',
         'Podfile':'ruby', 'Brewfile':'ruby', 'Appfile':'ruby', 'Fastfile':'ruby',
         'CMakeLists.txt':'cmake', 'Jenkinsfile':'groovy', '.metadata':'yaml'}
NAMES.update({name:'config' for name in ('.editorconfig','.coveragerc','.npmrc','.codespellrc','.sqlfluff')})
NAMES.update({name:'json' for name in ('.firebaserc','.babelrc','.swift-format','Srcfile')})
NAMES.update({name:'bash' for name in ('gradlew','mvnw','.envrc')})
NAMES.update({name:'starlark' for name in ('BUILD','WORKSPACE','MODULE')})
NAMES.update({'Kustomization':'yaml','config.ru':'ruby','.luacheckrc':'lua','.luacov':'lua','jvm.config':'properties','.bazelrc':'properties','Procfile':'procfile','justfile':'just','.goconvey':'properties'})
NAMES.update({'envVarTest':'shell_cases','wordsTest':'shell_cases'})
ASSETS = set('png jpg jpeg gif webp ico avif mp3 mp4 mov wav woff woff2 ttf otf pdf zip gz bz2 xz tar 7z jar class pyc so dylib dll exe a o bin db sqlite sqlite3 lock'.split())
DOCS = {'.md', '.rst', '.adoc', '.txt', '.csv', '.tsv', '.markdown', '.asciidoc', '.rdoc', '.ronn'}
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
    if suffix in {'.tfplan', '.patch', '.diff', '.strings', '.rc'} or name == 'tfplan':
        return {'kind':'data', 'language':None, 'reason':'Plan, patch or platform resource data; retained outside the control-flow score'}
    if suffix in {'.sha256','.sha512','.gliffy','.excalidraw','.snap','.stderr','.bench','.replay','.api','.sln','.pro','.list','.csr','.crt','.srl','.expected'} or name.endswith('.sum') or name in {'METADATA','vendor.conf'}:
        return {'kind':'data','language':None,'reason':'Recorded metadata, reference output or dependency data; fingerprinted outside source coverage'}
    if name in LOCKS or name.endswith('.min.js') or name.endswith('.min.css') or name.endswith('.map'):
        return {'kind':'generated', 'language':None, 'reason':'Generated or dependency lock file'}
    if name == '.env' or name.startswith('.env.') or suffix in {'.pem', '.key', '.p12', '.pfx'}:
        return {'kind':'opaque', 'language':'configuration', 'reason':'Sensitive configuration; metadata only'}
    language = NAMES.get(name) or ('dockerfile' if name.startswith('Dockerfile.') else 'make' if name.startswith(('Makefile.','GNUmakefile.')) else None) or EXTENSIONS.get(suffix)
    if not language and suffix in {'.example', '.sample', '.template', '.dist'}:
        language = EXTENSIONS.get(PurePosixPath(path.stem).suffix.lower())
    if language:
        return {'kind':'source', 'language':language, 'reason':None}
    if suffix in DOCS | {'.mdc'} or name.lower().startswith(('license','licence','copying','readme')) or name.lower() in {'notice','authors','contributors','patents','maintainers','codeowners','owners','security_contacts','dco','changelog','version','.mailmap','.gitattributes','.git-blame-ignore-revs','.bazelversion','.node-version','rust-toolchain','.gitkeep','.nojekyll'} or name.startswith('.') and name.endswith(('ignore','ignore-revs')):
        return {'kind':'documentation', 'language':None, 'reason':'Documentation or repository metadata'}
    if suffix.lstrip('.') in ASSETS | {'ai','eps','eot','snk','gpg','binpb','pb'}:
        return {'kind':'asset', 'language':None, 'reason':'Binary or packaged asset'}
    return {'kind':'unknown', 'language':'unknown', 'reason':'Unrecognized file type; metadata only'}
