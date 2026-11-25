"""Bound console output and report retained assets; never delete user content."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import threading
import time
from urllib.parse import unquote, urlsplit
import zipfile

class RuntimeHandler(RotatingFileHandler):
    def handleError(self, record):
        # Logging failures must not recurse through the redirected stderr.
        try:sys.__stderr__.write('Desk-Pal runtime log write failed.\n')
        except Exception:pass

class LogStream:
    encoding='utf-8'
    def __init__(self, logger, level, original):
        self.logger,self.level,self.original=logger,level,original
        self.buffer='';self.lock=threading.RLock()
    def write(self, text):
        with self.lock:
            if self.original.isatty():self.original.write(text)
            self.buffer+=text
            while '\n' in self.buffer or len(self.buffer)>=4096:
                if '\n' in self.buffer and self.buffer.index('\n')<4096:
                    line,self.buffer=self.buffer.split('\n',1)
                else:line,self.buffer=self.buffer[:4096],self.buffer[4096:]
                self.logger.log(self.level,line.rstrip('\r'))
        return len(text)
    def flush(self):
        with self.lock:
            if self.buffer:self.logger.log(self.level,self.buffer);self.buffer=''
            for handler in self.logger.handlers:handler.flush()
            if self.original.isatty():self.original.flush()
    def isatty(self):return False


def install_runtime_logging(root, max_bytes=1_000_000, backups=3):
    folder=Path(root)/'logs';folder.mkdir(parents=True,exist_ok=True)
    logger=logging.Logger('deskpal.runtime');logger.propagate=False
    handler=RuntimeHandler(folder/'deskpal-runtime.log',maxBytes=max_bytes,backupCount=backups,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    originals=(sys.stdout,sys.stderr)
    streams=(LogStream(logger,logging.INFO,sys.stdout),LogStream(logger,logging.ERROR,sys.stderr))
    sys.stdout,sys.stderr=streams
    def close():
        for stream in streams:stream.flush()
        sys.stdout,sys.stderr=originals;handler.close()
    return close


def asset_report(root):
    """Conservative inventory. Unreferenced means review, never safe to delete."""
    root=Path(root).resolve();assets=root/'assets';config=root/'config'
    files={p.relative_to(assets).as_posix():p for p in assets.rglob('*') if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(assets.resolve())}
    references=set();retained=set();errors=[]
    by_name={}
    for name in files:by_name.setdefault(Path(name).name,[]).append(name)
    def inspect(value):
        if isinstance(value,dict):
            for k,v in value.items():inspect(k);inspect(v)
        elif isinstance(value,list):
            for v in value:inspect(v)
        elif isinstance(value,str):
            try:path=unquote(urlsplit(value).path).replace('\\','/')
            except ValueError:return
            if path.startswith('/assets/'):references.add(path[8:])
            elif path.startswith('assets/'):references.add(path[7:])
            # Backgrounds are stored as theme-local filenames; retain all matches.
            elif Path(path).name==path and path in by_name:references.update(by_name[path])
            elif path.startswith(str(assets).replace('\\','/')+'/'):references.add(path[len(str(assets))+1:])
    for p in sorted(config.glob('*.json')):
        try:inspect(json.loads(p.read_text(encoding='utf-8')))
        except (ValueError,OSError):errors.append('Could not inspect config/'+p.name)
    # Theme defaults and authoring sheets are deliberate retained source assets.
    for name in files:
        lower=name.lower()
        if Path(lower).stem.startswith(('background','reference')) or 'sheet' in Path(lower).stem or '/references/' in '/'+lower:retained.add(name)
    for archive in (root/'backups').rglob('*.zip'):
        if archive.is_symlink():continue
        try:
            with zipfile.ZipFile(archive) as z:
                retained.update(n[7:] for n in z.namelist() if n.startswith('assets/'))
        except (OSError,zipfile.BadZipFile):errors.append('Could not inspect backup '+archive.name)
    def items(names):return [dict(path=n,bytes=files[n].stat().st_size) for n in sorted(names & files.keys())]
    stale=[]
    for p in config.glob('*.tmp'):
        if p.is_file() and not p.is_symlink() and time.time()-p.stat().st_mtime>86400:stale.append(dict(path='config/'+p.name,bytes=p.stat().st_size))
    return dict(read_only=True,warning='Unreferenced assets require human review; source files and recovery backups are retained. Nothing is deleted.',referenced=items(references),retained_sources=items(retained-references),unreferenced_review=items(files.keys()-references-retained),missing_references=sorted(references-files.keys()),stale_temporary_review=stale,inspection_errors=errors)
