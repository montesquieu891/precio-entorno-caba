"""Arma la carpeta que se despliega en Vercel, con el código confirmado y los datos locales.

    python scripts/preparar_vercel.py              # solo arma .vercel-build/
    python scripts/preparar_vercel.py --desplegar  # la arma y la despliega a producción

`--desplegar` corre la CLI sin acceso al repositorio Git: si la CLI adjunta el commit, Vercel bloquea el
despliegue porque el autor del commit no es miembro del proyecto.

- Código: lo confirmado en HEAD (`git archive`), no el árbol de trabajo, para no publicar cambios a medias.
  Se suma `precio_entorno/vercel_app.py` del disco por si todavía no se confirmó.
- Datos: las bases reales (copiadas con la API de respaldo de SQLite, consistentes aunque estén abiertas),
  las capas del mapa, el catálogo de cocheras, los CSV anuales del Mapa del Delito y el radar. No se copian `.env`, crudos de
  captura ni la app de Streamlit.
- Conserva `.vercel/`, donde la CLI guarda a qué proyecto está vinculada la carpeta.

La web es pública desde el 17/11/2026: las fuentes autorizan mostrar sus avisos. Si alguna retira el
permiso, sacar sus avisos o volver a activar la protección (ver docs/despliegue-vercel.md).
"""

import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.vercel-build'
CODE = ('precio_entorno', 'web', 'data/fixtures')
DATA = {
    'data/processed/entorno': '*',
    'data/local/radar': '**/*',
    'data/local': 'cocheras.json',  # catálogo autorizado de cocheras mensuales (docs/cocheras.md)
    'data/raw': 'delitos_20[0-9][0-9].csv',
}
BASES = ('real.sqlite3', 'real-alquiler.sqlite3')
VERCEL_CLI = 'vercel@65.15.0'
PYPROJECT = '''[project]
name = "precio-entorno-caba"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastapi>=0.115,<1", "numpy>=1.26,<3", "matplotlib>=3.8,<4", "httpx>=0.27,<1"]

[tool.vercel]
entrypoint = "precio_entorno.vercel_app:app"
'''
VERCEL_JSON = '''{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "functions": {
    "precio_entorno/vercel_app.py": {
      "includeFiles": "{data/**,web/**}",
      "excludeFiles": "{tests/**,**/__pycache__/**}"
    }
  }
}
'''


def clean(out):
    out.mkdir(exist_ok=True)
    for child in out.iterdir():
        if child.name == '.vercel':
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()


def export_code(out):
    archive = subprocess.run(['git', 'archive', '--format=tar', 'HEAD', *CODE], cwd=ROOT,
                             capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(out, filter='data')
    shutil.copyfile(ROOT / 'precio_entorno/vercel_app.py', out / 'precio_entorno/vercel_app.py')


def copy_data(out):
    for folder, pattern in DATA.items():
        for path in (ROOT / folder).glob(pattern):
            if path.is_file():
                target = out / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
    (out / 'data/local').mkdir(parents=True, exist_ok=True)
    for name in BASES:
        source = ROOT / 'data/local' / name
        if not source.exists():
            sys.exit(f'Falta {source}. Importá primero el catálogo real.')
        with sqlite3.connect(source) as src, sqlite3.connect(out / 'data/local' / name) as dst:
            src.backup(dst)
        dst.close()
        src.close()


def deploy(out):
    if not (out / '.vercel/project.json').exists():
        sys.exit('La carpeta no está vinculada a un proyecto de Vercel. Ver docs/despliegue-vercel.md.')
    # Sin Git a la vista, la CLI no adjunta el commit (ver la nota del principio).
    env = dict(os.environ, GIT_DIR=str(out / '.sin-git'), GIT_CEILING_DIRECTORIES=str(out.parent))
    npx = shutil.which('npx') or sys.exit('Falta npx (Node.js).')
    subprocess.run([npx, '-y', VERCEL_CLI, 'deploy', '--prod', '--yes', '--cwd', str(out)], env=env, check=True)


def main():
    clean(OUT)
    export_code(OUT)
    copy_data(OUT)
    (OUT / 'pyproject.toml').write_text(PYPROJECT, encoding='utf-8')
    (OUT / '.python-version').write_text('3.13\n', encoding='utf-8')
    (OUT / 'vercel.json').write_text(VERCEL_JSON, encoding='utf-8')
    size = sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file() and '.vercel' not in p.parts)
    print(f'Carpeta lista: {OUT} ({size / 1e6:.1f} MB)')
    if '--desplegar' in sys.argv[1:]:
        deploy(OUT)


if __name__ == '__main__':
    main()
