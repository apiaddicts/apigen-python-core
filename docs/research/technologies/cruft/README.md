# Generación con Cruft

## Instalación
```bash
pip install cruft
```

## Archivos Creados para Ejecución
Igual que CookieCutter, actualiza `resources/MasterTemplate/cookiecutter.json`.

## Ejecución
Desde la raíz del repositorio:
```bash
python3 technologies/cruft/generate.py
```

## Resultado
El proyecto se genera en la carpeta `output/`.
- `hospital_api_cruft/`: La aplicación.
- Si la ejecución CLI es exitosa, se incluye un archivo `.cruft.json` dentro del proyecto generado.

## Problemas/Limitaciones
- `cruft` está diseñado para trabajar con repositorios Git. Si la plantilla local no es un repo git, puede fallar o requerir flags especiales.
- En este ejemplo, si `cruft` falla, el script hace fallback a `cookiecutter` estándar para asegurar que se genere algo.

## Comparativa
- **Cruft** vs **CookieCutter**:
    - Cruft **ES** CookieCutter + Gestión de Estado.
    - El resultado es idéntico al de CookieCutter, PERO añade `.cruft.json`.
    - Este archivo permite ejecutar `cruft update` en el futuro para traer cambios de la plantilla sin perder el trabajo manual (si hay conflictos, git ayuda a resolverlos).
