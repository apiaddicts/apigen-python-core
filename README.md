# Generador de API Hospital (ODS Examples)

Este repositorio contiene ejemplos de cómo generar una API FastAPI basada en una especificación OpenAPI (`api-hospital.yaml`) utilizando 4 tecnologías de templating diferentes.

El objetivo es demostrar las diferencias, ventajas y desventajas de cada herramienta.

## Estructura del Proyecto

```text
.
├── Dockerfile                  # Para ejecutar todos los generadores fácilmente
├── COMPARISON.md               # Comparativa detallada de las herramientas
├── resources/                  # Archivos compartidos
│   ├── MasterTemplate/         # Plantilla base Jinja2
│   ├── api-hospital.yaml       # Especificación OpenAPI
│   └── ...
└── technologies/               # Generadores específicos
    ├── cookiecutter/
    ├── copier/
    ├── cruft/
    └── pyscaffold/
```

## Tecnologías Utilizadas

1.  **CookieCutter**: El estándar de facto. Simple y efectivo.
2.  **Copier**: Más moderno, permite actualizaciones inteligentes.
3.  **Cruft**: Wrapper de CookieCutter con gestión de estado (git-friendly).
4.  **PyScaffold**: Generador de estructura de proyectos robusta.

Puedes ver una comparativa detallada en [COMPARISON.md](COMPARISON.md).

## Cómo Ejecutar

### Opción 1: Docker (Recomendada)

Hemos preparado un contenedor que tiene todas las herramientas instaladas.

1.  **Construir la imagen**:
    ```bash
    docker build -t hospital-generators .
    ```

2.  **Ejecutar los generadores**:
    Montamos el volumen `technologies` para que los archivos generados aparezcan en tu máquina local.
    ```bash
    docker run -v $(pwd)/technologies:/app/technologies hospital-generators
    ```

    Esto ejecutará los 4 generadores secuencialmente. Verás los resultados en `technologies/{herramienta}/output/`.

### Opción 2: Ejecución Manual

Requiere Python 3.10+ y las dependencias instaladas.

1.  **Instalar dependencias**:
    ```bash
    pip install cookiecutter copier cruft pyscaffold pyyaml
    ```

2.  **Ejecutar un generador específico**:
    ```bash
    python3 technologies/cookiecutter/generate.py
    # o
    python3 technologies/copier/generate.py
    # etc.
    ```

## Verificación

Para asegurarte de que todo se ha generado correctamente, puedes ejecutar el script de verificación:

```bash
python3 resources/verify_generation.py
```

## Documentación Específica

Cada carpeta en `technologies/` tiene su propio `README.md` con detalles sobre cómo funciona esa herramienta específica:

- [CookieCutter README](technologies/cookiecutter/README.md)
- [Copier README](technologies/copier/README.md)
- [Cruft README](technologies/cruft/README.md)
- [PyScaffold README](technologies/pyscaffold/README.md)

Se escoge copier, se desarrolla un template y se publica como paquete

# Cómo usarlo en otros repositorios:
### Instalar: 
Puedes instalarlo directamente desde este git (si subes los cambios) o desde tu carpeta local:

```bash
pip install git+https://gitlab.com/cloudappi/clo-innova/opendataspace/ods-data-generator-examples.git@develop#subdirectory=package
```
Usar en código:

```python
from apigen_copier import generate_project
generate_project(
    yaml_path="mi-api.yaml",
    output_dir="mi-proyecto-generado"
)
```