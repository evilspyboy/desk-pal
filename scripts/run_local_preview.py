"""Run the real Desk-Pal renderer in an isolated, browser-accessible PC installation."""
import argparse,json,os,runpy,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def prepare_installation(directory,backup=None):
    directory=Path(directory).resolve()
    if directory==ROOT or directory in ROOT.parents or any(directory.is_relative_to(ROOT/name) for name in ('src','config','assets','scripts')):raise ValueError('Choose a separate installation directory')
    directory.mkdir(parents=True,exist_ok=True)
    config=directory/'config/room_config.json'
    if not config.exists():
        if backup is None:raise ValueError('First launch needs --backup pointing to a Desk-Pal backup ZIP')
        sys.path.insert(0,str(ROOT/'src'))
        from backup_packages import unpack,destination,encoded
        _,cfg,files=unpack(Path(backup).read_bytes())
        for name,body in files.items():
            if name=='config/room_config.json':continue
            target=destination(name,directory/'assets',directory/'config');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
        # A preview uses simulated updates, never automatic external polling or stale-feed alarms.
        for app in cfg.get('apps',[]):app['source_enabled']=False;app['monitor_health']=False
        config.parent.mkdir(parents=True,exist_ok=True)
        config.write_bytes(encoded(cfg))
    source=directory/'src';source.mkdir(exist_ok=True)
    for path in (ROOT/'src').iterdir():
        if path.is_file() and path.suffix in ('.py','.html','.js'):shutil.copy2(path,source/path.name)
    return directory

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data-dir',default=str(ROOT/'local-preview'));parser.add_argument('--backup');parser.add_argument('--starter',action='store_true',help='Initialize using bundled generic scenes/animations instead of a personal backup');parser.add_argument('--port',type=int,default=7779);args=parser.parse_args()
    if args.starter and args.backup:parser.error('Choose --starter or --backup')
    if args.starter:args.backup=str(ROOT/'examples/starter-content.zip')
    if not 1024<=args.port<=65535:parser.error('Use a port between 1024 and 65535')
    directory=prepare_installation(args.data_dir,args.backup)
    sys.path.insert(0,str(directory/'src'))
    try:
        import pygame
    except ImportError:
        sys.path.insert(0,str(ROOT/'scratch/local_preview_deps'))
        try:import pygame
        except ImportError:raise SystemExit('Install pygame with the Python interpreter used to run this preview.')
    os.environ['DESKPAL_LOCAL_PREVIEW']='1';os.environ['DESKPAL_PREVIEW_PORT']=str(args.port);os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
    os.chdir(directory)
    print('Local data:',directory,flush=True);print('Editor and live preview: http://127.0.0.1:'+str(args.port),flush=True)
    runpy.run_path(str(directory/'src/deskpal_app.py'),run_name='__main__')

if __name__=='__main__':main()
