"""Fetch the original PointQ engine at the version used by the experiments."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'vendor/pointq'
COMMIT='769af12f47da7bbfe29570fd6c9da479e10381cb'
if TARGET.exists():
    actual=subprocess.check_output(['git','-C',str(TARGET),'rev-parse','HEAD'],text=True).strip()
    if actual!=COMMIT:
        raise RuntimeError('An existing PointQ directory has a different version. Preserve it and use a fresh directory.')
else:
    TARGET.parent.mkdir(exist_ok=True)
    subprocess.run(['git','-c','core.longpaths=true','clone','--no-checkout','https://github.com/akurzhan/point-q.git',str(TARGET)],check=True)
    subprocess.run(['git','-C',str(TARGET),'config','core.longpaths','true'],check=True)
    subprocess.run(['git','-C',str(TARGET),'checkout','--detach',COMMIT],check=True)
print('PointQ source ready at the verified study commit.')
