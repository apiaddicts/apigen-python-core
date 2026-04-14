# Generación con Copier

## Instalación
```bash
pip install copier pyyaml
```

## Archivos Creados para Ejecución
Se realiza una conversión al template de la `MasterTemplate` (formato CookieCutter) a un formato compatible con Copier:
1.  Crea una copia del template `MasterTemplate` en `CopierTemplate`.
2.  Genera `copier.yml` con la configuración.
3.  Renombra `{{cookiecutter.project_slug}}` a `{{project_slug}}`.
4.  Elimina el prefijo `cookiecutter.` de las variables en los archivos.

## Ejecución
Desde la raíz del repositorio:
```bash
python3 technologies/copier/generate.py
```

## Resultado
El proyecto se genera en la carpeta `output/` dentro de este directorio.
- `hospital_api_copier/`: La aplicación FastAPI completa.

## Problemas/Limitaciones
- Requiere adaptación de la plantilla si esta fue diseñada exclusivamente para CookieCutter (como es nuestro caso).
- La sintaxis de variables es ligeramente diferente (`{{var}}` vs `{{cookiecutter.var}}`).

## Comparativa
- **Copier** vs **CookieCutter**:
    - Usa `copier.yml` en lugar de `cookiecutter.json`.
    - Permite pasar datos complejos (diccionarios/listas) vía API de Python de forma más nativa.
    - Soporta actualizaciones inteligentes (diffs) si se regenera el proyecto (aunque este script borra la salida cada vez para demostración).
