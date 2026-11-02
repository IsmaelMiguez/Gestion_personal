# Gestion_personal

Proyecto de aplicación portable para Windows destinada a gestión y cálculo de nóminas, con evolución progresiva hacia RRHH.

La propuesta completa, las restricciones, las decisiones pendientes y un prompt para nuevas conversaciones están en [ARQUITECTURA_Y_CONTEXTO.md](ARQUITECTURA_Y_CONTEXTO.md).

Estado actual: backend de registro de personal, listado con búsqueda HTMX, ficha con histórico contractual, formulario conjunto de alta y edición de datos personales. Motor de cálculo y distribución Windows pendientes.

## Desarrollo del frontend

Bootstrap está declarado y bloqueado mediante pnpm en `src/frontend/`. Para reconstruir sus archivos locales:

```bash
corepack pnpm --dir src/frontend install --frozen-lockfile
node src/frontend/scripts/prepare-static.mjs
```

El script también está disponible como `corepack pnpm --dir src/frontend run prepare:static`. Copia los recursos compilados y la licencia a `src/frontend/static/vendor/bootstrap/`. Estos archivos se conservan en el repositorio; `node_modules/` queda excluido. HTMX se sirve desde los recursos locales de `django-htmx`, sin CDN.

Para abrir la página inicial:

```bash
uv run python src/manage.py runserver 127.0.0.1:8000
```

Visita `http://127.0.0.1:8000/` y entra en Empleados (`/employees/`). Listado y fichas requieren una cuenta activa con acceso de administrador (`is_staff`); si no hay sesión se solicita acceso mediante el login existente de Django. El listado permite buscar y paginar; la ficha muestra los contratos y periodos de condiciones, con importes en euros. Pulsa Registrar empleado (`/employees/new/`) para introducir datos personales, contrato y condiciones en una sola operación. Selecciona una empresa existente; si no hay ninguna, el formulario enlaza con Administración para crearla. Un error impide guardar todo el registro y conserva los datos introducidos. Desde la ficha, Editar datos personales permite corregir identidad y documento sin cambiar contratos ni retribuciones; Cancelar vuelve a la ficha sin guardar.

## Comprobaciones

```bash
uv run ruff check src/
uv run ruff format --check src/
uv run python src/manage.py test backend.employees
uv run python src/manage.py check
```
