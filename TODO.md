# API Generator — Trabajo Pendiente

## ✅ Completado

- [x] CRUD completo (GET, POST, PUT, DELETE)
- [x] Relaciones nivel 2 con `$expand` (multi-nivel: `owner.address`)
- [x] `$select` — selección de campos (compatible con `$expand`)
- [x] `$orderby` — ordenamiento multi-campo
- [x] `$limit` / `$offset` — paginación
- [x] Response schemas — modelos parciales como filtro de salida
- [x] Error response schemas — modelos de error con `default` values
- [x] Composite keys — PKs multi-columna
- [x] Smart mapping — array ↔ JSON string auto-serialización
- [x] Status codes personalizados (201, 204, etc.)
- [x] Sub-routers — rutas anidadas (`/users/{id}/roles`)
- [x] Tipos: String, Integer, Long, Boolean, Date, DateTime, Decimal, Float, Array

---

## 🔴 Alta Prioridad

- [ ] **PATCH** — Solo hay PUT (replace). Falta PATCH (partial update)
- [ ] **Request validation** — `required`, `minLength`, `maxLength`, `enum`, `pattern` del OpenAPI → generar `Field()` de Pydantic
- [ ] **Pagination metadata** — Devuelve `[{...}]` crudo. Debería ser `{data:[], total:N, limit, offset}`

## 🟡 Media Prioridad

- [ ] **Filtering por campos** — `?status=active&name=John`. No existe filtrado dinámico
- [ ] **Request body parcial** — POST/PUT siempre usa modelo completo. Debería respetar el `requestBody` del OpenAPI (misma lógica que response schemas)
- [ ] **Enum types** — Si OpenAPI define `enum: [active, inactive]`, generar Python Enum

## 🟢 Baja Prioridad

- [ ] **Auth/Security schemes** — `bearerAuth`, `apiKey` del OpenAPI
- [ ] **File upload** — `multipart/form-data`
- [ ] **Soft delete** — patrón de borrado lógico
- [ ] **Búsqueda** — full-text search
