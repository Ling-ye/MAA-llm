"""Check deliverable paths and likely secrets without printing secret values."""
from pathlib import Path
import argparse, json, re, subprocess
ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','__pycache__','.venv','venv','.pytest_cache','config.local','tools','downloads','state','runs','evidence','debug','logs'}
BAD_SUFFIX={'.png','.jpg','.jpeg','.webp','.gif','.exe','.dll','.zip','.7z','.apk','.msi','.log','.jsonl','.pyc','.out','.err'}
TEXT_SUFFIX={'.py','.ps1','.json','.md','.txt','.toml','.yml','.yaml'}
MAX_SIZE=1024*1024
RULES={
 'github_token':re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})'),
 'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'service_key':re.compile(r'\b(?:sk-[A-Za-z0-9_-]{25,}|AKIA[A-Z0-9]{16})\b'),
 'credential_url':re.compile(r"""https?://[^/\s:@\'"]+:[^/\s@\'"]+@"""),
 'bearer_value':re.compile(r'(?i)authorization\s*[:=]\s*["\']?(?:bearer|basic)\s+[A-Za-z0-9_./+=-]{12,}'),
 'personal_windows_path':re.compile(r'(?i)\b[A-Z]:[/\\]+Users[/\\]+(?!Public\b|Default\b)[^/\\\s"\']+'),
 'source_machine_path':re.compile(r'(?i)\b[DE]:[/\\]+(?:MAA|MuMu|python-\d)'),
 'email_address':re.compile(r'\b[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
 'phone_number':re.compile(r'(?<!\w)1[3-9]\d{9}(?!\w)'),
}
def inspect(paths,root=ROOT):
    issues=[];count=0;total=0
    for path in sorted(paths):
        path=Path(path);relative=path.relative_to(root);count+=1
        if any(part in SKIP for part in relative.parts) or path.suffix.lower() in BAD_SUFFIX or path.name=='STOP' or path.name.startswith('cleanup-'):
            issues.append({'path':relative.as_posix(),'rule':'runtime_or_binary'});continue
        if path.suffix.lower() not in TEXT_SUFFIX and path.name not in {'.gitignore','.gitattributes','LICENSE'}:
            issues.append({'path':relative.as_posix(),'rule':'unreviewed_file_type'});continue
        size=path.stat().st_size;total+=size
        if size>MAX_SIZE:
            issues.append({'path':relative.as_posix(),'rule':'large_file'});continue
        try: content=path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            issues.append({'path':relative.as_posix(),'rule':'non_utf8'});continue
        for rule,regex in RULES.items():
            for hit in regex.finditer(content):
                issues.append({'path':relative.as_posix(),'rule':rule,'line':content.count('\n',0,hit.start())+1})
    return {'files':count,'bytes':total,'issues':issues,'ok':not issues}
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tracked',action='store_true');p.add_argument('--git',default='git');a=p.parse_args(argv)
    if a.tracked:
        raw=subprocess.check_output([a.git,'-C',str(ROOT),'ls-files','-z'])
        paths=[ROOT/name.decode('utf8') for name in raw.split(b'\0') if name]
    else:
        paths=[p for p in ROOT.rglob('*') if p.is_file() and not any(x in SKIP for x in p.relative_to(ROOT).parts)]
    result=inspect(paths)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ok'] else 2
if __name__=='__main__':raise SystemExit(main())
