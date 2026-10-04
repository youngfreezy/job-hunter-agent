"""Preserve safe budget-stop reasons through Stagehand's JSON-RPC boundary."""
from stagehand.rpc_client import RPCError

from backend.shared.model_budget import BudgetStopped

CEILING_STOP = 'Model spend ceiling reached; paid request blocked.'
BUDGET_STOP = 'Model budget verification stopped; paid requests blocked. Existing reservations are retained.'


def budget_stop_message(error: Exception) -> str | None:
    """Do not expose arbitrary RPC/provider messages or infer stops from substrings."""
    if isinstance(error, BudgetStopped):
        return CEILING_STOP if str(error) == CEILING_STOP else BUDGET_STOP
    if isinstance(error, RPCError) and error.code == -32603:
        if str(error) in (CEILING_STOP, BUDGET_STOP):
            return str(error)
    return None
