# Comparativa de Herramientas de Generación

Este documento compara las 4 tecnologías utilizadas para generar la API Hospital.

## Resumen

| Herramienta | Tipo | Actualizable? | Complejidad | Caso de Uso Ideal |
| :--- | :--- | :--- | :--- | :--- |
| **CookieCutter** | Plantilla Jinja2 | No (nativamente) | Baja | Proyectos simples, "fire and forget". |
| **Copier** | Plantilla + Datos + Diff | Sí (Inteligente) | Media | Proyectos que evolucionan, plantillas con lógica. |
| **Cruft** | Wrapper de CookieCutter | Sí (Git-based) | Media | Si ya usas CookieCutter y quieres actualizaciones futuras. |
| **PyScaffold** | Bootstrapper | Sí (Estructura) | Alta | Paquetes Python profesionales, librerías, ciencia de datos. |

## Detalles

### 1. CookieCutter
- **Qué es**: El estándar de la industria. Simplemente renderiza una plantilla Jinja2.
- **Pros**: Muy fácil de crear plantillas. Gran ecosistema.
- **Contras**: Una vez generado el proyecto, se pierde el vínculo con la plantilla. Actualizar es manual y doloroso.
- **Diferencia**: Es la base de comparación.

### 2. Copier
- **Qué es**: Una evolución moderna. Usa `copier.yml` y preguntas interactivas (o datos por CLI).
- **Pros**: 
    - **Actualizaciones**: Puede reaplicar la plantilla sobre un proyecto existente respetando cambios manuales (usando algoritmos de diff).
    - **Lógica**: Permite ejecutar código Python y filtros complejos en la plantilla.
- **Contras**: Menos popular que CookieCutter (aunque creciendo). Sintaxis ligeramente diferente.
- **Diferencia**: Usa `{{var}}` en vez de `{{cookiecutter.var}}`.

### 3. Cruft
- **Qué es**: Un "pegamento" entre CookieCutter y Git.
- **Pros**: Te da lo mejor de CookieCutter (ecosistema) con la capacidad de actualizar (feature de Copier). Crea un archivo `.cruft.json` con el hash del commit de la plantilla.
- **Contras**: Dependencia fuerte de Git.
- **Diferencia**: Es idéntico a CookieCutter en la generación, pero añade `.cruft.json`.

### 4. PyScaffold
- **Qué es**: Un generador de estructura de proyectos, no solo un renderizador de plantillas.
- **Pros**: Configura todo el entorno de desarrollo profesional (`tox`, `pre-commit`, `pytest`, `setup.cfg`).
- **Contras**: Muy opinado. Difícil de personalizar si no te gusta su estructura.
- **Diferencia**: Genera una estructura de carpetas muy diferente (`src/package/`). Lo usamos en combinación con CookieCutter para inyectar el código de la API.
