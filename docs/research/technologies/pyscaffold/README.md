# Generación con PyScaffold

## Instalación
```bash
pip install pyscaffold cookiecutter
```

## Archivos Creados para Ejecución
- Utiliza `putup` (CLI de PyScaffold) para la estructura base.
- Utiliza `cookiecutter` y `MasterTemplate` para generar el contenido de la API en una carpeta temporal.

## Ejecución
Desde la raíz del repositorio:
```bash
python3 technologies/pyscaffold/generate.py
```

## Resultado
El proyecto se genera en la carpeta `output/`.
- `hospital_api_pyscaffold/`: Proyecto con estructura estándar de paquete Python.
    - **Nota**: Se ven muchos más archivos que en los otros ejemplos (`setup.cfg`, `tox.ini`, `docs/`, `tests/`).
    - Esto es porque PyScaffold genera un entorno profesional completo para empaquetado y distribución, no solo el código de la API.
    - Nuestro código generado (modelos, rutas) se inyecta dentro de `src/hospital_api_pyscaffold/`.

## Problemas/Limitaciones
- PyScaffold es muy opinado sobre la estructura del proyecto.
- Requiere un paso extra de "overlay" (copiar archivos encima) para inyectar nuestra lógica personalizada generada por CookieCutter.

## Comparativa
- **PyScaffold** vs **CookieCutter**:
    - CookieCutter te da un lienzo en blanco (o lo que defina tu plantilla).
    - PyScaffold te da una estructura profesional de Python pre-configurada (packaging, testing, docs setup).
    - Aquí usamos un enfoque híbrido: PyScaffold para el esqueleto, CookieCutter para la carne (API).
