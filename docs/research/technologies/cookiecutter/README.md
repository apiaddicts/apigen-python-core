# Generación con CookieCutter

## Instalación
```bash
pip install cookiecutter
```

## Archivos Creados para Ejecución
Este script actualiza automáticamente `resources/MasterTemplate/cookiecutter.json` con los metadatos del proyecto antes de ejecutar la generación.

## Ejecución
Desde la raíz del repositorio:
```bash
python3 technologies/cookiecutter/generate.py
```

## Resultado
El proyecto se genera en la carpeta `output/` dentro de este directorio.
- `hospital_api_cookiecutter/`: La aplicación FastAPI completa.

## Problemas/Limitaciones
- No tiene gestión de estado nativa. Si la plantilla cambia, no hay forma fácil de actualizar el proyecto generado sin sobrescribir cambios manuales.

## Comparativa
- **CookieCutter** es la base.
- Se usa la plantilla `MasterTemplate` directamente.
- Es el enfoque más simple y directo.
