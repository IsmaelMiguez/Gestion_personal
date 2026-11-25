"""Arithmetic reconciliation of supported payrolls, not legal certification."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .base_salary import _calculation_context
from .ordinary_payroll import OrdinaryPayroll


@dataclass(frozen=True, slots=True)
class BalanceCheck:
    label: str
    equation: str
    difference: Decimal

    @property
    def balanced(self) -> bool:
        return self.difference == 0


def reconcile_ordinary_payroll(
    payroll: OrdinaryPayroll, rounding: str
) -> tuple[BalanceCheck, ...]:
    """Expose each independent balance without masking discrepancies."""
    with localcontext(_calculation_context(rounding)):
        return (
            BalanceCheck(
                "Composición del bruto",
                "Bruto − base − antigüedad − complemento",
                payroll.gross_amount
                - payroll.salary.ordinary_payment_amount
                - payroll.seniority_amount
                - payroll.fixed_supplement_amount,
            ),
            BalanceCheck(
                "Descuento de seguros",
                "Total seguros − seguro trabajador/familia registrado como exento − registrado como sujeto",
                payroll.insurance_amount
                - payroll.insurance_exempt_amount
                - payroll.insurance_taxable_amount,
            ),
            BalanceCheck(
                "Valoración fiscal",
                "Base IRPF − bruto dinerario",
                payroll.taxable_gross_amount - payroll.gross_amount,
            ),
            BalanceCheck(
                "Cotización teórica",
                "Base sin tope − bruto − prorrata de extras",
                payroll.uncapped_contribution_base
                - payroll.gross_amount
                - payroll.extra_payment_accrual,
            ),
            BalanceCheck(
                "Cuotas trabajador",
                "Total trabajador − suma de sus cuotas",
                payroll.employee_contributions
                - sum(
                    (line.employee_amount for line in payroll.contributions),
                    Decimal(0),
                ),
            ),
            BalanceCheck(
                "Cuotas empresa",
                "Total empresa − suma de sus cuotas",
                payroll.employer_contributions
                - sum(
                    (line.employer_amount for line in payroll.contributions),
                    Decimal(0),
                ),
            ),
            BalanceCheck(
                "Fiscalidad",
                "Total fiscal − retención dineraria",
                payroll.withholding_amount - payroll.cash_withholding_amount,
            ),
            BalanceCheck(
                "Líquido antes de seguros",
                "Bruto − SS trabajador − IRPF − líquido previo a seguros",
                payroll.gross_amount
                - payroll.employee_contributions
                - payroll.withholding_amount
                - payroll.net_before_insurance,
            ),
            BalanceCheck(
                "Líquido",
                "Líquido previo − seguros − transferencia",
                payroll.net_before_insurance
                - payroll.insurance_amount
                - payroll.net_amount,
            ),
            BalanceCheck(
                "Coste empresarial",
                "Coste − bruto − cuotas empresa",
                payroll.employer_cash_cost
                - payroll.gross_amount
                - payroll.employer_contributions,
            ),
        )
