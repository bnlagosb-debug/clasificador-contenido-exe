# Clasificador por contenido (carpetas 200/250/500/600/...)

Este paquete incluye:
- clasificador_por_contenido.py
- config.json (ejemplo)

## Ejecutar (Windows)
1) Instala Python 3.10+ (marca "Add Python to PATH").
2) Abre PowerShell en esta carpeta y ejecuta:
   python clasificador_por_contenido.py --config .\config.json

## Crear EXE en tu PC (PyInstaller)
   pip install pyinstaller
   pyinstaller --onefile --noconsole --name ClasificadorContenido clasificador_por_contenido.py

El EXE queda en .\dist\ClasificadorContenido.exe
