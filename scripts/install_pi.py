"""Preview or install Desk-Pal for the current Raspberry Pi desktop user."""
import argparse, json, os, platform, re, shutil, subprocess
from pathlib import Path, PurePosixPath
from run_local_preview import ROOT, prepare_installation

def plan(home, directory=None):
    home=PurePosixPath(home)
    directory=PurePosixPath(directory) if directory else home/'.local/share/deskpal'
    for path in (home,directory):
        if not path.is_absolute() or '..' in path.parts or not re.fullmatch(r'/[A-Za-z0-9_./-]+',str(path)):
            raise ValueError('Use absolute Linux paths without spaces or shell characters')
    if directory == home or not directory.is_relative_to(home) or home == PurePosixPath('/'):
        raise ValueError('Choose a dedicated installation subdirectory inside the user home')
    unit='''[Unit]
Description=Desk-Pal animated application monitor
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory={data}
Environment=DESKPAL_DATA_DIR={data}
Environment=DESKPAL_STUDIO_URL=http://localhost:7777
ExecStart=/usr/bin/python3 {data}/src/deskpal_app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical-session.target
'''.format(data=directory)
    launcher='''#!/bin/sh
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_RUNTIME_DIR
exec systemctl --user start deskpal.service
'''
    desktop='''[Desktop Entry]
Type=Application
Name=Desk-Pal
Comment=Start Desk-Pal after desktop login
Exec={data}/start-desktop.sh
Terminal=false
'''.format(data=directory)
    return {'data_directory':str(directory),'service_path':str(home/'.config/systemd/user/deskpal.service'),'autostart_path':str(home/'.config/autostart/deskpal.desktop'),'unit':unit,'launcher':launcher,'desktop':desktop,'packages':['python3-pygame','python3-gpiozero','python3-tz','tzdata']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',default=str(Path.home()))
    parser.add_argument('--data-dir')
    parser.add_argument('--apply',action='store_true',help='Install for the current Linux desktop user; otherwise print a plan')
    parser.add_argument('--install-dependencies',action='store_true',help='Use sudo apt-get to install runtime packages with --apply')
    args=parser.parse_args()
    result=plan(args.home,args.data_dir)
    if not args.apply:
        print(json.dumps(result,indent=2));return
    if platform.system()!='Linux' or os.geteuid()==0:
        parser.error('Run --apply as the ordinary Linux desktop user, not root')
    if Path(args.home).resolve()!=Path.home().resolve():
        parser.error('--apply must use the current user home')
    if args.install_dependencies:
        subprocess.run(['sudo','apt-get','update'],check=True)
        subprocess.run(['sudo','apt-get','install','-y']+result['packages'],check=True)
    subprocess.run(['/usr/bin/python3','-c','import pygame, gpiozero; from zoneinfo import ZoneInfo; ZoneInfo("Australia/Brisbane")'],check=True)
    directory=Path(result['data_directory'])
    for name in ('deskpal.service','deskpal.desktop'):
        path=Path(result['service_path'] if name.endswith('.service') else result['autostart_path'])
        if path.exists() and 'Desk-Pal' not in path.read_text():
            raise SystemExit('Refusing to overwrite an unrelated file: '+str(path))
    # Updating source while the renderer writes configuration would be unsafe.
    subprocess.run(['systemctl','--user','stop','deskpal.service'],check=False)
    prepare_installation(directory,ROOT/'examples/starter-content.zip')
    for key,text in (('service_path','unit'),('autostart_path','desktop')):
        path=Path(result[key]);path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():shutil.copy2(path,path.with_suffix(path.suffix+'.previous'))
        path.write_text(result[text],encoding='utf-8')
    launcher=directory/'start-desktop.sh';launcher.write_text(result['launcher'],encoding='utf-8');launcher.chmod(0o755)
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','deskpal.service'],check=True)
    print('Installed at',directory)
    print('Start after desktop login:',launcher)
    print('Editor: http://YOUR-PI:7777/ . Settings and assets are retained on later installs.')

if __name__=='__main__':main()
