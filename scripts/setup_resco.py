"""Fetch the source benchmark version used for the corridor projection."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'vendor/RESCO'
COMMIT='f1ed9a174f8de41fc9d8689373b836bc882570dc'
if TARGET.exists():
    actual=subprocess.check_output(['git','-C',str(TARGET),'rev-parse','HEAD'],text=True).strip()
    if actual!=COMMIT:
        raise RuntimeError('The existing RESCO source has a different version. Use a fresh directory.')
else:
    TARGET.parent.mkdir(exist_ok=True)
    subprocess.run(['git','clone','--no-checkout','https://github.com/Pi-Star-Lab/RESCO.git',str(TARGET)],check=True)
    subprocess.run(['git','-C',str(TARGET),'checkout','--detach',COMMIT],check=True)
print('RESCO source ready. extract_resco.py also checks both source XML hashes.')
