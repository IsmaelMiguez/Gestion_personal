# Gestion_personal

Proyecto de aplicación portable para Windows destinada a gestión y cálculo de nóminas, con evolución progresiva hacia RRHH.

La propuesta completa, las restricciones, las decisiones pendientes y un prompt para nuevas conversaciones están en [ARQUITECTURA_Y_CONTEXTO.md](ARQUITECTURA_Y_CONTEXTO.md).

Estado actual: acceso propio mediante Django, sección Nóminas con registro/consulta/edición de empleados y espacio independiente reservado para Gestión documental. Motor independiente con sueldo base, antigüedad, extras y nómina ordinaria del caso soportado. Cálculo de nómina completa, funciones documentales y distribución Windows pendientes.

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

`/payroll/employees/` contiene el listado con búsqueda y paginación. Desde Registrar empleado (`/payroll/employees/new/`) se guardan datos personales, contrato y condiciones conjuntamente; selecciona una empresa existente o créala antes desde **Registrar empresa** (`/payroll/companies/new/`). El formulario solicita nombre e identificación fiscal única y deja la empresa disponible para altas y filtros de nóminas. La ficha permite editar datos personales sin modificar contratos ni salarios. Cada periodo tiene Cambiar condiciones: solicita una fecha interior al periodo, cierra el anterior ese día y crea otro conservando el fin previsto. Añadir condiciones permite registrar periodos nuevos sin solapamientos.

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

Cada fila identifica empresa, trabajador, relación laboral y mes. Se consultan las condiciones que cubren todo el intervalo activo del mes. El sueldo base, la antigüedad y el complemento fijo se prorratean con el mes estándar; las cotizaciones e IRPF de periodos incompletos se calculan con los días aplicables. El líquido de esos meses descuenta cada prima proporcionalmente a los días salariales sobre 30. Pulsa una celda para abrir la card con valor, fórmula/origen, operandos, regla y redondeo. Las tarjetas se obtienen de los mismos resultados que la tabla; si cambian los filtros hay que recalcular. Los importes son euros y los tipos son porcentajes (en particular F muestra 100, no la fracción 1 del Excel).

Los conceptos no implementados permanecen **Pendientes**, con el motivo en su detalle. No se copian los importes sintéticos del libro. El informe calcula el caso ordinario de 2026: jornada completa o parcial con horas reales introducidas para el mes, Régimen General, contrato indefinido ordinario y grupos mensuales 1–7, con periodos completos o altas/bajas parciales. El formulario exige declarar ausencia de incidencias, bonus, pluriempleo, bonificaciones, horas complementarias/extraordinarias, trabajo concentrado y cotizaciones especiales. No se deduce esa ausencia de los datos del contrato.

Para los totales hacen falta sueldo/pagas, IRPF, grupo y AT/EP. Los seguros deben estar informados explícitamente, con 0 si no existen; el caso soportado descuenta los seguros del líquido después de calcular SS e IRPF sobre el bruto completo. El complemento fijo se paga en dinero cada uno de los doce meses, además del sueldo base, y se integra en la nómina. Si faltan importes, cambios de condiciones dentro del mes o un ejercicio/régimen no soportado, los totales quedan pendientes; los datos de contrato que sí se conocen se muestran con su origen. Se simula el abono de extras y el control aritmético general. En altas/bajas parciales se calculan sueldo base, antigüedad, complemento fijo, bruto y devengo de extras. Sus cotizaciones e IRPF ya se calculan; el líquido de periodos incompletos descuenta cada prima por días salariales / 30. Ajustes, NCM, INSS, bonus y regularizaciones quedan para los siguientes incrementos. El selector completo no implica que el motor ya implemente todas esas reglas.

Pruebas de esta vista: `uv run python src/manage.py test backend.employees.tests.test_payroll_report`.


## Antigüedad: primer incremento

`src/payroll_engine/seniority.py` implementa el perfil inicial expresamente acordado: 0–1 años 0 %, 2–3 5 %, 4–5 10 %, 6–7 15 %, 8–9 20 %, 10–14 25 %, 15 35 %, 16–19 40 %, 20–21 50 %, 22–23 55 % y 24 o más 60 %. No se presenta como regla universal de todos los convenios.

La pantalla **Calcular nóminas** muestra G (porcentaje) y P (importe mensual), con detalle de su origen. P = (sueldo base por paga ordinaria + los cuatro seguros mensuales registrados) × porcentaje / 100. El complemento fijo no se incluye. Los importes ya pertenecen a la jornada habitual y no se aplica otra reducción por jornada. Un seguro sin informar no se sustituye por cero: puede conocerse G, pero P queda pendiente hasta informar los cuatro seguros.

Los cambios de tramo se aplican desde el primer día del mismo mes en que se alcanza la antigüedad, aunque el aniversario caiga al final del mes. Los aniversarios del 29 de febrero se aplican en febrero también en años no bisiestos, porque la regla depende del mes y no del día. Fechas posteriores al mes calculado y cantidades inválidas se rechazan explícitamente.

La antigüedad alimenta la referencia de extras, el devengo semestral y la nómina ordinaria soportada: sueldo base más antigüedad, con descuentos de seguros informados y complemento fijo dinerario mensual. No requiere migraciones ni nuevas dependencias.


## Composición de las pagas extraordinarias

Confirmado por el usuario: **solo sueldo base y antigüedad**. Los cuatro seguros no se suman directamente a la extra, pero sí participan en el importe de antigüedad según la regla anterior. El complemento fijo queda excluido.

`payroll_engine/extra_payments.py` calcula una referencia para condiciones constantes. Con 14 pagas, la referencia por extra es sueldo base ordinario + antigüedad mensual; la referencia anual de extras es el doble y la prorrata mensual es ese total dividido por 12, con redondeo explícito. La diferencia anual de redondeo se conserva sin asignarla a un pago. Con 12 pagas no hay extras separadas ni se añade otra prorrata, porque los conceptos ya se distribuyen en las ordinarias.

En **Calcular nóminas**, la columna I y su tarjeta muestran esa prorrata y los operandos, incluso cuando otras partidas de la nómina siguen pendientes. Si no se conoce la antigüedad, la referencia de 14 pagas queda pendiente. En 12 pagas la ausencia de prorrata adicional se conoce independientemente de las partidas monetarias pendientes.

La referencia de la columna I no sustituye el devengo semestral que se muestra aparte, ni registra un pago efectivo. Las altas/bajas ya se contemplan en el devengo de extras; las incidencias y las variaciones de cotización todavía no soportadas siguen pendientes. La nómina ordinaria integra la antigüedad en SS/IRPF/neto dentro del alcance descrito al final; los casos incompletos permanecen pendientes. No requiere migraciones ni dependencias nuevas.


## Devengo semestral de extras

Tras calcular la tabla aparece **Devengo semestral de extras**, por empresa, trabajador, relación laboral y año. Cada mes seleccionado consulta su semestre completo: enero–junio para la extra de julio y julio–diciembre para diciembre. Julio también consulta el semestre anterior, para mostrar la extra correspondiente a ese mes. Seleccionar varios meses del mismo semestre no duplica su panel. La tarjeta de la columna I también permite consultar el desglose de su semestre.

Se utilizan las condiciones vigentes de **cada mes**, aunque ese mes no figure entre los filtros de la tabla. Con catorce pagas, el importe es la suma de (sueldo base mensual + antigüedad mensual) × días salariales / 180. Cada mes completo aporta 30 días y el mes del alta/baja aporta los días del calendario estándar, también en febrero. Los meses fuera de la relación aportan cero sin requerir un contrato ficticio. Con seis meses completos equivale a dividir entre seis la suma de referencias mensuales. Se admiten cambios de sueldo, jornada contractual o antigüedad entre meses cuando cada mes tiene condiciones únicas y un porcentaje de antigüedad estable. No se vuelve a multiplicar el sueldo por la jornada: ya representa el importe contratado. Los seguros solo intervienen mediante la antigüedad y el complemento fijo no se añade a la extra.

El total se redondea una sola vez con la política seleccionada. El panel muestra además los devengos mensuales redondeados, su suma y la diferencia necesaria para conciliar con el total. Esa diferencia no se asigna automáticamente a un mes. En doce pagas durante todo el semestre no hay otra extra separada: el resultado es cero, sin duplicar importes.

Si faltan condiciones para cubrir un intervalo activo, hay solapamientos, faltan datos de sueldo/seguros o cambia la modalidad entre 12 y 14 pagas, se explica el motivo y no se muestra una suma parcial como extra completa. El formulario exige confirmar ausencia de incidencias en los **periodos y semestres consultados**. Si el semestre no ha terminado en la fecha de consulta, el resultado se identifica como **proyección según las condiciones registradas**.

El motor independiente está en `payroll_engine/semester_extras.py` y su lectura del histórico en `backend/employees/payroll_semester.py`. La consulta no modifica la base de datos, no registra pagos. Se simula el IRPF y líquido de la extra por separado, sin repetir las cotizaciones mensuales. La columna I conserva su referencia mensual; la cotización de la nómina ordinaria utiliza la estimación anual separada explicada a continuación. Sin migraciones ni dependencias nuevas.


## Nómina ordinaria con antigüedad y extras estimadas

La vista **Calcular nóminas** integra ahora sueldo base + antigüedad en bruto, cuotas, IRPF informado, líquido y coste empresarial. Se mantiene el alcance de jornada completa o parcial con horas informadas, grupos mensuales 1–7 y contrato indefinido ordinario del Régimen General en 2026. Los cuatro seguros se descuentan del líquido en el perfil confirmado que se detalla a continuación. El complemento fijo se abona en dinero cada uno de los doce meses; se integra en bruto, cotización, IRPF y neto, sin incluirse en extras ni antigüedad. Cualquier dato obligatorio ausente impide publicar un total incompleto.

La [Orden PJC/297/2026, artículo 1](https://www.boe.es/buscar/act.php?id=BOE-A-2026-7296#a1) establece la parte proporcional de extras sobre el importe anual estimado; para retribución mensual se divide entre 12. Para 14 pagas, la aplicación suma las dos extras semestrales calculadas con las condiciones registradas de cada mes. Esto utiliza el ejercicio completo aunque los filtros solo muestren enero. Las condiciones futuras abiertas se proyectan según su vigencia registrada; no se reconstruye qué información se conocía originalmente en una nómina pasada ni se hacen regularizaciones automáticas. Si falta un semestre calculable, el total ordinario queda pendiente con su motivo. Cuando la relación no cubre el año completo, la referencia diaria se estima dividiendo el devengo anual previsto entre los días salariales cubiertos por la relación; se aplica a los días cotizados del mes. No se usa sin más el devengo parcial anual dividido entre doce. Es una estimación según el histórico y proyección registrados, sin regularizaciones retroactivas.

- **I:** referencia mensual de extras a condiciones constantes del mes.
- **J:** bruto ordinario + I, como equivalente mensual de referencia antes de los descuentos del líquido.
- **X:** estimación de julio + diciembre normalizada por el tiempo salarial cubierto y aplicada a los días cotizados. Con año completo y 30 días cotizados equivale al anual dividido entre 12.
- **Z/AB:** bruto ordinario + X, antes de topes; AC aplica el mínimo/máximo común, y las cuotas profesionales utilizan su base correspondiente.
- **W:** sueldo ordinario + antigüedad + complemento fijo, sin pagar otra vez la prorrata ni incluir la extra separada.
- **AE:** bruto ordinario completo; las primas no reducen la base fiscal.
- **BV/BY, BZ, CA/CB:** cuotas de trabajador/empresa, retención informada, líquido ordinario y bruto ordinario más cuotas de empresa.

I y X pueden diferir si cambian sueldo o antigüedad entre meses. Al pulsar X, Z o AC se muestran ambos semestres y el origen de la estimación anual. En 12 pagas no se añade una segunda prorrata: los conceptos ya se distribuyen en las ordinarias; no hace falta completar el año para calcular el mes, pero una transición registrada entre 12 y 14 pagas bloquea los totales hasta definirla. La declaración de ausencia de incidencias del formulario abarca también el ejercicio usado en la estimación.

El IRPF se aplica al bruto ordinario satisfecho con el tipo ya informado, conforme al [artículo 80 del Reglamento del IRPF](https://www.boe.es/buscar/act.php?id=BOE-A-2007-6820#a80); no se resta antes la cuota de SS ni se calcula el tipo. En julio/diciembre el líquido de esta tabla sigue siendo el de la paga ordinaria, sin añadir el pago separado de la extra. No se cambia el reparto contractual ni se suman primas de seguros como dinero.

El motor conserva `calculate_ordinary_payroll_2026` para el simulador manual de solo sueldo base y reutiliza la misma lógica para `calculate_ordinary_payroll_with_seniority_2026`, que recibe antigüedad mensual y extras anuales estimadas explícitas. No se incorporan parámetros flag ni valores por defecto. Sin modelos, migraciones o dependencias nuevas.


## Seguros descontados del líquido

La aclaración del 25/11/2026 sustituye el perfil anterior de retribución flexible. Primero se calcula la nómina completa sobre sueldo base + antigüedad + complemento fijo; después se descuentan del líquido las cuatro primas pagadas por el trabajador. **Los seguros no sustituyen sueldo dinerario, no reducen las bases de SS o IRPF y no generan ingreso a cuenta** en este perfil.

- **AE:** bruto ordinario completo.
- **BZ:** bruto ordinario × tipo IRPF informado, redondeado una sola vez.
- **CA/CG:** bruto − SS trabajador − IRPF − las cuatro primas.
- **CB:** bruto + cuotas de empresa. Las primas no se suman al coste.

Las denominaciones históricas exento/sujeto se conservan para identificar los importes guardados; no producen efectos fiscales diferentes. Se conserva la base de antigüedad previamente confirmada: sueldo base más los cuatro seguros. No se modifican importes almacenados ni se convierte un campo vacío en cero.

`calculate_ordinary_payroll_with_insurance_deductions_2026` sustituye el nombre del calculador de flexibilidad y comparte el cálculo ordinario existente. El resultado expone `net_before_insurance` y `net_amount`. Las tarjetas muestran ambos líquidos y el descuento; un saldo negativo se conserva con aviso, sin ocultarlo o convertirlo en cero. Las primas ausentes o inválidas se rechazan.

Por ejemplo, con 2.000 € de sueldo base, sin antigüedad ni complemento, las bases y retenciones son las de 2.000 €; si las primas suman 100 €, la transferencia es el líquido calculado menos 100 €. El cálculo automático del tipo IRPF y otros perfiles de seguros quedan fuera de este incremento.

## Complemento fijo, conciliación y abono de extras

El usuario confirma el complemento fijo como importe mensual **en dinero, adicional al sueldo base y pagado doce veces al año**, independientemente de que el sueldo base se reparta en 12 o 14 pagas. Entra en bruto, bases de SS y retención dineraria, sin incorporarse a la base de antigüedad ni al devengo/prorrata de extras. La columna U y el desglose de bruto muestran su origen. No se convierte en un importe por paga ni se vuelve a anualizar para añadirlo otra vez. La función `calculate_ordinary_payroll_with_insurance_deductions_2026` exige ahora `fixed_supplement` explícito; los calculadores anteriores proporcionan cero expresamente.

**CJ · Control general** muestra OK/REVISAR y permite abrir diez balances independientes: composición del bruto, seguros, valoración fiscal, base teórica, cuotas de cada pagador, retención, líquido previo, transferencia y coste. Se muestran diferencias sin ocultarlas ni corregirlas automáticamente. Un OK solo acredita identidades aritméticas del supuesto calculado; no valida normativa, exenciones, tipo de IRPF o cobertura de NCM. Los controles específicos de INSS/14–12 del Excel conservan su estado pendiente donde falta la regla.

El panel de cada semestre añade **Simulación de abono** para catorce pagas: extra bruta, IRPF informado de julio/diciembre y líquido separado. Se usa el porcentaje del **mes de pago**, no la media de los meses de devengo ([RIRPF, artículos 78 y 80](https://www.boe.es/buscar/act.php?id=BOE-A-2007-6820#a78)). No se repiten seguros mensuales, complemento fijo ni cuotas SS ya contempladas en la prorrata mensual ([Orden PJC/297/2026, artículo 1](https://www.boe.es/buscar/act.php?id=BOE-A-2026-7296#a1)). No es una nómina ordinaria adicional ni un registro de transferencia bancaria.

Para calcular ese líquido debe existir una relación y condiciones únicas que cubran el mes de pago, en el perfil mensual ordinario soportado de 2026, con catorce pagas e IRPF informado. Si el tipo cambia dentro del mes o no puede establecerse, el bruto devengado conocido se conserva y el abono queda pendiente de concretar la fecha efectiva. En doce pagas no hay abono adicional. Las proyecciones de semestres abiertos siguen identificadas como tales.

Estos cambios no añaden modelos ni migraciones, y no modifican datos de desarrollo. Los aniversarios ya aplican en el mismo mes. El divisor de altas/bajas se ha confirmado en 30 y `prorate_monthly_salary` calcula importe mensual ÷ 30 × días explícitos, redondeando solo el resultado final. El usuario confirma febrero como mes estándar: un alta el día 15 hasta fin de febrero cuenta 16 días. La columna O ya muestra el sueldo base parcial usando las fechas de la relación y condiciones únicas para todo el intervalo activo. Su tarjeta explica días y operación. El fin de la relación es exclusivo: una baja efectiva el día 15 se registra con fin el 16. El día 31 se normaliza al día 30; un mes sin relación aporta cero días. La antigüedad y el complemento fijo ya se prorratean con sus importes mensuales de referencia, y el bruto parcial suma los tres conceptos devengados. Las extras ponderan cada mes por sus días / 180. Las cotizaciones e IRPF del periodo ya se calculan. El líquido de periodos incompletos ya descuenta cada prima proporcionalmente a los días salariales sobre 30. I/J siguen siendo referencias de mes completo. NCM/INSS y bonus/regularizaciones conservan su alcance pendiente.


## Origen del complemento fijo en el Excel

El campo procede de `EMPLEADOS!P3` («Complemento fijo») y se representa en `CALCULO_2026!U3` («Compl. fijo»). Revisados los 24 registros de empleados y los 336 valores de cálculo de esa columna: todos son cero. No existe un ejemplo con complemento fijo positivo en el libro. Se conserva como concepto opcional y, conforme al acuerdo previo, se paga en dinero doce veces al año, fuera de antigüedad y extras. Informar cero si no existe.


## Devengos de altas y bajas en meses incompletos

La tabla muestra O (sueldo base), P (antigüedad) y U (complemento fijo) prorrateados por días / 30; W suma los tres importes redondeados. P parte de la antigüedad mensual calculada con la base acordada y el tramo del propio mes del aniversario. No se vuelve a reducir por la jornada del contrato. Las tarjetas muestran el importe mensual y los días aplicados. Un importe desconocido mantiene pendiente su partida y cualquier suma dependiente.

El panel semestral incluye días / 30 y distingue bases mensuales de referencia del devengo de cada mes. Se suman las referencias × días / 180 antes de redondear el total; los meses sin relación tienen cero días y cero devengo. Se conserva la diferencia frente a la suma de devengos mensuales redondeados. El complemento fijo y los seguros no se añaden directamente a la extra. En doce pagas no hay otra extra separada.

Tras una baja se puede conocer el devengo bruto sin simular un pago en julio/diciembre ni un finiquito. Los cambios de sueldo, primas y complemento dentro del intervalo activo ya se desglosan por tramos; las variaciones de jornada/cotización todavía no soportadas y las transiciones 12/14 permanecen pendientes. Las cotizaciones ya están integradas. El líquido de un mes incompleto con primas positivas descuenta cada seguro proporcionalmente a los días salariales sobre 30.


## Cotización de periodos incompletos

Se distinguen días salariales y días cotizados. El salario conserva el mes estándar de 30 días pactado, incluido febrero. Para el supuesto ordinario mensual sin incidencias, la cotización usa 30 días si existe alta todo el mes y días naturales de alta en meses incompletos. Por ejemplo, un alta el 15 de febrero de 2026 hasta fin de mes tiene 16 días salariales y 14 cotizados. Fuente: [TGSS, reglas de control de bases con ajuste mensual, apartados 1 y 6](https://www.seg-social.es/wps/wcm/connect/wss/b86a3dba-9bce-4c87-9d0c-f357d382a76b/Reglas%2Bpara%2Bdeterminar%2Bel%2Bcontrol%2Bde%2Bbases%2Bcon%2Bajuste%2Bmensual.pdf?MOD=AJPERES).

`calculate_period_contributions_2026` recibe el bruto devengado sin volver a prorratearlo, las extras previstas, los días salariales cubiertos del año y los días cotizados. Normaliza la referencia estimada de extras por los días salariales cubiertos y la multiplica por los cotizados del mes. Con condiciones constantes evita que un alta a mitad de año reduzca indebidamente la referencia diaria. La base teórica es bruto + prorrata; aplica los límites del grupo proporcionales a los días cotizados y los tramos de solidaridad escalados al mismo periodo. Las cuotas existentes de CC, MEI, desempleo, FP, FOGASA y AT/EP se reutilizan. Fuentes: [Orden PJC/297/2026, artículos 1–3 y 17](https://www.boe.es/buscar/act.php?id=BOE-A-2026-7296).

Las columnas de cotización, IRPF informado y coste se muestran cuando sus datos están disponibles. En meses completos se descuentan las primas mensuales conocidas; en meses incompletos cada prima se multiplica por los días salariales / 30 y se redondea antes de sumar los descuentos. Un campo desconocido mantiene pendientes los resultados dependientes. La card de cada resultado del periodo muestra días salariales/cotizados, días salariales de la estimación anual, fórmula de prorrata y límites aplicados. El cálculo no incluye finiquito, cotización de vacaciones no disfrutadas ni regularizaciones. El control general CJ y el desglose ordinario completo conservan su alcance anterior; no se publican artificialmente como controles completados del periodo.


## Seguros en meses incompletos

El usuario confirma el descuento proporcional sobre 30 días. Q/R/S/T muestran cada prima mensual × días salariales / 30, con el redondeo elegido para cada seguro antes de sumar. CA/CG restan exactamente esos cuatro valores al líquido previo a seguros, después de SS e IRPF. En febrero se aplica el calendario salarial estándar: 100 € de prima mensual y un alta el día 15 hasta fin de mes producen un descuento de 53,33 € por 16 días salariales, aunque para cotizar correspondan 14 días naturales en 2026. No se vuelven a prorratear las primas al calcular el líquido, ni se modifican las bases fiscales o de cotización. Las cantidades mensuales del contrato y la base mensual de antigüedad previamente acordada se conservan.


## Jornada parcial con horas introducidas por mes

La vista Calcular nóminas permite introducir las horas ordinarias realmente trabajadas en cada fila de jornada parcial (por relación laboral, año y mes). Primero se calcula la tabla, se completan las horas y se pulsa **Recalcular con horas**. Las entradas se conservan al recalcular y se envían al abrir una celda con HTMX o un POST normal. No se guardan en la base de datos: al abrir una consulta nueva hay que introducirlas otra vez. Las filas de jornada completa no requieren este dato.

El sueldo base sigue siendo el de la jornada contractual. Un contrato al 50 % con 1.000 € mensuales mantiene esos 1.000 € antes de otros conceptos y, cuando proceda, del prorrateo por alta/baja. No se deducen horas a partir del porcentaje ni se aplican otra vez ese porcentaje al salario o al límite máximo de cotización.

`calculate_part_time_contributions_2026` calcula los mínimos a partir de las horas del periodo: mínimo común según grupo y mínimo profesional por hora. Se reutilizan prorrata de extras, cuotas, topes y solidaridad del motor actual; el resultado conserva los mínimos aplicados para que las tarjetas reflejen las cifras utilizadas. Fuente: [Orden PJC/297/2026, artículos 38–39](https://www.boe.es/buscar/act.php?id=BOE-A-2026-7296#a3-10). Se mantienen los grupos mensuales 1–7 y el indefinido ordinario del Régimen General en 2026. Quedan fuera incidencias, horas complementarias/extraordinarias, pluriempleo y trabajo concentrado.

Las horas deben ser positivas, finitas y con hasta dos decimales, y no pueden superar las horas naturales del intervalo activo. Vacío, cero, negativos o datos inválidos no se sustituyen por una estimación: se muestran errores y la cotización/líquido dependientes permanecen pendientes. Los seguros continúan descontándose por días salariales / 30; esas primas no se prorratean otra vez por horas. Las extras mantienen el devengo acordado y el pago separado con IRPF informado. El calendario automático y el almacenamiento de horas siguen fuera de este incremento, por decisión expresa. Sin migraciones ni dependencias nuevas.


## Cambios de condiciones dentro del mes

**Alcance actualizado el 26/11/2026:** el usuario aplaza esta casuística. No se ampliará su implementación ni se pedirán horas por tramo. El escenario prioritario mantiene una jornada contractual fija y distingue una reducción temporal por permiso sobre esa jornada. El desarrollo previo que se describe a continuación queda como antecedente técnico, sin ampliaciones en este incremento.

La tabla divide las vigencias que cubren el intervalo activo y suma O/P/Q/R/S/T/U/W por tramos. Cada importe del tramo se calcula con los días salariales estándar asignados y se redondea una vez. La tarjeta muestra fechas, días salariales/cotizados, sueldo mensual de referencia y conceptos devengados. Los días se reparten de forma acumulativa: no se añaden días por tener varios registros y el cambio del día 31 puede recibir cero días salariales. En febrero se conserva el cierre estándar a 30.

Las extras admiten varias referencias dentro de un mes. Se suman referencias × días / 180 sin redondear antes el total semestral. Las filas del semestre incluyen el intervalo de cada tramo. No se ocultan huecos o solapamientos y no se publica una suma incompleta como una nómina o extra cerrada. Las transiciones entre 12 y 14 pagas siguen pendientes.

Este primer incremento cierra las cuotas para cambios de sueldo, seguros y complemento con jornada completa y grupo/tipo AT-EP constantes. Los mínimos se comprueban por tramo; después se aplica una sola vez el máximo mensual. La solidaridad parte de la remuneración sin tope del mes y no de las bases elevadas por mínimos. Fuente: [TGSS, control de bases con ajuste mensual, apartados 2 y 6](https://www.seg-social.es/wps/wcm/connect/wss/b86a3dba-9bce-4c87-9d0c-f357d382a76b/Reglas%2Bpara%2Bdeterminar%2Bel%2Bcontrol%2Bde%2Bbases%2Bcon%2Bajuste%2Bmensual.pdf?MOD=AJPERES).

Con un tipo IRPF informado común se aplica al bruto mensual y se redondea una sola vez. Si el tipo cambia dentro del mes, BZ/CA/CG permanecen pendientes de conocer el pago, sin repartir tipos por fechas de devengo ni regularizarlos automáticamente. Fuente: [RIRPF, artículo 78](https://www.boe.es/buscar/act.php?id=BOE-A-2007-6820#a78). Cambios de grupo o AT/EP dejan pendientes las cuotas; en tramos de jornada parcial hacen falta horas por tramo, pues el total mensual no permite comprobar el mínimo de cada vigencia. Se consulta al usuario antes de introducir ese nuevo reparto manual.

Se reutilizan los modelos y el motor existentes; payroll_segments.py separa la lectura y presentación del caso con varias condiciones. No se añaden entidades persistentes, dependencias ni migraciones. CJ mantiene su alcance anterior y no se certifica el nuevo caso como conciliado sin implementar esos controles.
