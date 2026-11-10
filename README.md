# Gestion_personal

Proyecto de aplicación portable para Windows destinada a gestión y cálculo de nóminas, con evolución progresiva hacia RRHH.

La propuesta completa, las restricciones, las decisiones pendientes y un prompt para nuevas conversaciones están en [ARQUITECTURA_Y_CONTEXTO.md](ARQUITECTURA_Y_CONTEXTO.md).

Estado actual: acceso propio mediante Django, sección Nóminas con registro/consulta/edición de empleados y espacio independiente reservado para Gestión documental. Primer cálculo del motor independiente: reparto de sueldo base anual/mensual. Cálculo de nómina completa, funciones documentales y distribución Windows pendientes.

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

`/payroll/employees/` contiene el listado con búsqueda y paginación. Desde Registrar empleado (`/payroll/employees/new/`) se guardan datos personales, contrato y condiciones conjuntamente; selecciona una empresa existente o créala antes desde Administración. La ficha permite editar datos personales sin modificar contratos ni salarios. Cada periodo tiene Cambiar condiciones: solicita una fecha interior al periodo, cierra el anterior ese día y crea otro conservando el fin previsto. Añadir condiciones permite registrar periodos nuevos sin solapamientos.

La ficha también permite Eliminar periodo y Eliminar empleado. Ambas operaciones requieren abrir una confirmación y marcar expresamente la casilla. Eliminar un empleado incluye sus contratos y condiciones, conservando empresas y otros empleados. Eliminar un periodo no extiende los vecinos y puede dejar un intervalo sin condiciones.

`/documents/` solo muestra una página de sección pendiente. No tiene operaciones documentales ni depende de las vistas de empleados. La API `/api/` y el administrador `/admin/` conservan sus rutas. Las antiguas pantallas `/employees/…` se han trasladado bajo `/payroll/`.

## Comprobaciones

```bash
uv run ruff check src/
uv run ruff format --check src/
uv run python src/manage.py test backend.employees frontend.pages
uv run python src/manage.py check
```

Las pruebas del módulo de empleados están agrupadas en `src/backend/employees/tests/`. Puedes ejecutarlas todas con `uv run python src/manage.py test backend.employees` o seleccionar un bloque, por ejemplo `uv run python src/manage.py test backend.employees.tests.test_edit`. Las pruebas de acceso y secciones están en `frontend.pages`.


## Motor Python independiente

`src/payroll_engine/base_salary.py` contiene el primer bloque de cálculo: reparto del sueldo base para un año completo con condiciones constantes, entre doce o catorce pagas. Antigüedad, seguros y complementos se añaden aparte; el importe registrado se ha confirmado como sueldo base.

- `base_salary_from_annual(amount, payments_per_year, rounding)` parte del sueldo base anual.
- `base_salary_from_monthly(amount, payments_per_year, rounding)` parte del sueldo base por paga ordinaria, con extras de base iguales en el caso de catorce pagas.
- `BaseSalaryBreakdown` devuelve anual, importe por ordinaria, número/importe de extras y diferencia de redondeo pendiente de distribuir. Esa diferencia no se aplica automáticamente a ningún pago.

Las entradas monetarias son `Decimal`; el redondeo debe indicarse explícitamente. Las pruebas usan `ROUND_HALF_UP` como ejemplo y `ROUND_DOWN` para comprobar que se respeta la política elegida: no se ha aprobado una política normativa de redondeo. El contexto decimal del cálculo es local y no depende de la configuración decimal de quien lo invoca.

Ejemplo de alcance: 28.000 € de sueldo base anual en catorce pagas produce doce ordinarias de 2.000 € y dos extras de base de 2.000 €, antes de otros conceptos o deducciones. Las extras se mantienen separadas del importe de una mensualidad ordinaria.

Para probar el motor sin configurar Django:

```bash
uv run python -m unittest discover -s src/payroll_engine/tests -t src
```

El reparto base no está conectado todavía a las pantallas. El importe ya corresponde a la jornada habitual del contrato: un sueldo mensual de 1.000 € para un contrato al 50 % se mantiene en 1.000 €, sin reducirlo otra vez. Las reducciones temporales se tratarán como incidencias relativas a esa jornada habitual, separadas de las condiciones contractuales. No se equipara automáticamente una reducción por cuidado de un hijo con NCM ni con otra situación: sus reglas se concretarán al implementar cada supuesto. La prueba portable Windows se pospone por decisión expresa del usuario.

### Primera nómina ordinaria de 2026

Vista de simulación: abre `/payroll/simulation/` desde **Nóminas → Simular nómina**, con una cuenta activa de personal. Introduce manualmente sueldo base anual, pagas, grupo mensual, IRPF, AT/EP y política de redondeo. El resultado muestra bruto y líquido destacados, bases, cuotas de trabajador/empresa y conciliación del neto. Funciona con HTMX y mediante POST normal; no guarda simulaciones ni modifica empleados. Este formulario representa únicamente el supuesto acotado descrito a continuación.

`ordinary_payroll.py` añade `calculate_ordinary_payroll_2026`: mes completo, jornada completa, contrato indefinido ordinario del Régimen General, cotización mensual (grupos 1–7), condiciones constantes y exclusivamente sueldo base. No se aplica a sistemas especiales, pluriempleo, bonificaciones, cotizaciones adicionales por jubilación, incidencias ni conceptos adicionales. El llamador debe comprobar ese alcance antes de usarlo con un empleado. No se ha conectado a empleados ni se han añadido campos o migraciones.

`rules_2026.py` separa bases, tipos y tramos de la fórmula, con referencia a la [Orden PJC/297/2026](https://www.boe.es/buscar/act.php?id=BOE-A-2026-7296), artículos 1–4, 16, 17 y 33. La versión es explícitamente 2026: no sirve como normativa de otros ejercicios. El grupo y el tipo total AT/EP se reciben expresamente; el tipo AT/EP debe verificarse según actividad/ocupación, no se deduce del nombre del puesto. El porcentaje IRPF ya determinado se aplica al bruto pagado, según el [artículo 80 del Reglamento del IRPF](https://www.boe.es/buscar/act.php?id=BOE-A-2007-6820#a80); no calcula ni regulariza dicho porcentaje.

El resultado devuelve prorrata de extras para cotización, bases antes y después de topes, cuotas desglosadas por concepto y pagador, retención y líquido. Las extras no se pagan en este resultado. `employer_cash_cost` es bruto ordinario más cuotas empresariales del mes; no incluye el devengo de extras pendiente de pago. La diferencia anual de redondeo permanece visible en `salary.annual_rounding_difference`, pendiente de una regla de distribución. Cada cuota y la prorrata se redondean a céntimos con la política recibida; debe contrastarse con el software oficial. Aplicar bases mínimas no certifica que el salario cumpla el SMI o el convenio.

Prueba práctica desde la raíz, sin arrancar Django ni modificar la base de datos:

```bash
PYTHONPATH=src uv run python - <<'PY'
from decimal import Decimal, ROUND_HALF_UP
from payroll_engine.ordinary_payroll import calculate_ordinary_payroll_2026

result = calculate_ordinary_payroll_2026(
    annual_base_salary=Decimal("28000.00"),
    payments_per_year=14,
    contribution_group=5,
    withholding_rate=Decimal("15.00"),
    occupational_risk_rate=Decimal("1.50"),
    rounding=ROUND_HALF_UP,
)
print("Bruto ordinario:", result.salary.ordinary_payment_amount)
print("Prorrata extras para cotización:", result.extra_payment_accrual)
for line in result.contributions:
    print(line.name, "base:", line.base,
          "trabajador:", line.employee_amount, "empresa:", line.employer_amount)
print("IRPF:", result.withholding_amount)
print("Líquido:", result.net_amount)
print("Bruto ordinario + cuotas empresa:", result.employer_cash_cost)
PY
```

Los tipos IRPF y AT/EP del ejemplo son entradas ilustrativas, no valores predeterminados ni una recomendación para un empleado concreto. Resultado: bruto 2.000,00 €, prorrata 333,33 €, cuota trabajador 151,67 €, cuota empresa 750,17 €, IRPF 300,00 € y líquido 1.548,33 €. Para partir de una cantidad mensual puede obtenerse el anual mediante `base_salary_from_monthly`; no se transforma a jornada completa.


## Cálculo por empresas y periodos

Abre **Nóminas → Calcular nóminas** (`/payroll/calculation/`). Antes del primer uso aplica la migración aditiva:

```bash
uv run python src/manage.py migrate
```

Las condiciones laborales incorporan grupo de cotización (1–11) y tipo total AT/EP (%), ambos opcionales para conservar los registros existentes sin inventar valores. Se editan al registrar/cambiar condiciones y desde Administración, y se exponen en la API. La base de datos limita los valores admitidos.

Selecciona empresas, sus trabajadores, años/meses y conceptos. Los trabajadores se actualizan con HTMX; el botón **Actualizar trabajadores** ofrece la alternativa mediante POST normal. Hay selección de todos/ninguno para trabajadores, meses y campos. Las 90 columnas de `CALCULO_2026` se conservan como catálogo estático A–CL, agrupadas por conceptos; no se necesita abrir el Excel para utilizar la aplicación. La consulta admite hasta 240 filas. No se guardan nóminas ni se modifican empleados.

Cada fila identifica empresa, trabajador, relación laboral y mes. Se consultan las condiciones que cubren ese mes completo y se reutiliza el motor ordinario. Pulsa una celda para abrir la card con valor, fórmula/origen, operandos, regla y redondeo. Las tarjetas se obtienen de los mismos resultados que la tabla; si cambian los filtros hay que recalcular. Los importes son euros y los tipos son porcentajes (en particular F muestra 100, no la fracción 1 del Excel).

Los conceptos no implementados permanecen **Pendientes**, con el motivo en su detalle. No se copian los importes sintéticos del libro. La primera versión calcula el caso ordinario de 2026: mes completo, jornada completa, Régimen General, contrato indefinido ordinario y grupos mensuales 1–7. El formulario exige declarar ausencia de incidencias, bonus, pluriempleo, bonificaciones y cotizaciones especiales. No se deduce esa ausencia de los datos del contrato.

Para los totales hacen falta sueldo/pagas, IRPF, grupo y AT/EP. Seguros y complemento fijo deben estar informados explícitamente con 0 para el caso base. Si faltan, son distintos de cero, hay antigüedad de dos años o más durante el mes, cambios dentro del mes o un ejercicio/régimen no soportado, los totales quedan pendientes; los datos de contrato que sí se conocen se muestran con su origen. Extras efectivamente pagadas, antigüedad, ajustes, NCM, INSS y controles del Excel necesitan sus siguientes incrementos de cálculo. El selector completo no implica que el motor ya implemente todas esas reglas.

Pruebas de esta vista: `uv run python src/manage.py test backend.employees.tests.test_payroll_report`.
