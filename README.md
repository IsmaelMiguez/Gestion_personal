# Gestion_personal

Proyecto de aplicación portable para Windows destinada a gestión y cálculo de nóminas, con evolución progresiva hacia RRHH.

La propuesta completa, las restricciones, las decisiones pendientes y un prompt para nuevas conversaciones están en [ARQUITECTURA_Y_CONTEXTO.md](ARQUITECTURA_Y_CONTEXTO.md).

Estado actual: acceso propio mediante Django, sección Nóminas con registro/consulta/edición de empleados y espacio independiente reservado para Gestión documental. Motor de cálculo, funciones documentales y distribución Windows pendientes.

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

Visita `http://127.0.0.1:8000/`: sin sesión abre `/login/`; con sesión entra en `/payroll/`. Utiliza tu cuenta activa de Django con `is_staff` (la cuenta administradora existente sirve). El acceso propio no requiere entrar en `/admin/`. Cerrar sesión envía un POST protegido por CSRF.

## Organización de páginas

```text
src/frontend/
├── pages/                     # Rutas, login y acceso compartido
└── templates/
    ├── base.html              # Marco común, sin URL propia
    ├── components/            # Fragmentos compartidos entre secciones
    └── pages/
        ├── login/index.html
        ├── payroll/
        │   ├── base.html      # Navegación propia de Nóminas
        │   ├── index.html
        │   ├── partials/
        │   └── employees/     # Listado, ficha, alta, edición y fragmentos
        └── documents/index.html
```

`/payroll/employees/` contiene el listado con búsqueda y paginación. Desde Registrar empleado (`/payroll/employees/new/`) se guardan datos personales, contrato y condiciones conjuntamente; selecciona una empresa existente o créala antes desde Administración. La ficha permite editar datos personales sin modificar contratos ni salarios.

`/documents/` solo muestra una página de sección pendiente. No tiene operaciones documentales ni depende de las vistas de empleados. La API `/api/` y el administrador `/admin/` conservan sus rutas. Las antiguas pantallas `/employees/…` se han trasladado bajo `/payroll/`.

## Comprobaciones

```bash
uv run ruff check src/
uv run ruff format --check src/
uv run python src/manage.py test backend.employees frontend.pages
uv run python src/manage.py check
```

Las pruebas del módulo de empleados están agrupadas en `src/backend/employees/tests/`. Puedes ejecutarlas todas con `uv run python src/manage.py test backend.employees` o seleccionar un bloque, por ejemplo `uv run python src/manage.py test backend.employees.tests.test_edit`. Las pruebas de acceso y secciones están en `frontend.pages`.
