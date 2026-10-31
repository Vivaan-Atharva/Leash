"""Dispute report: who is liable for a decision? Pure functions over stored, signed records."""
from shared.money import inr

PLAIN = {1: "identity", 2: "merchant", 3: "limits", 4: "intent", 5: "price", 6: "validity"}


def verdict(decision: dict, resolution: dict | None, revoked_at: str | None) -> dict:
    """Returns {headline, liability, tone}. tone: blocked | allowed | held."""
    outcome = decision["outcome"]
    failing = [c["n"] for c in decision.get("checks", []) if not c["pass"]]
    merchant = decision.get("merchant")
    if outcome == "HELD" and resolution is None:
        return {"headline": "Held for Asha's approval on her phone. No money has moved.",
                "liability": "Pending user approval", "tone": "held"}
    if resolution is not None:
        if resolution["outcome"] == "ALLOWED":
            return {"headline": f"Inside the mandate and approved on Asha's phone. "
                                f"{inr(resolution['amount_debited_paise'])} settled to {merchant}.",
                    "liability": "Approved by the user", "tone": "allowed"}
        why = "Asha denied it on her phone" if resolution["resolved_by"] == "phone" else \
            "no approval within 60 seconds"
        if resolution.get("error"):
            why = resolution["error"]
        return {"headline": f"Held for approval: {why}. No money moved. User not liable.",
                "liability": "User not liable", "tone": "blocked"}
    if outcome == "ALLOWED":
        return {"headline": f"Inside the mandate: all checks passed. {inr(decision['amount_debited_paise'])} "
                            f"settled to {merchant} under Asha's signed mandate.",
                "liability": "Covered by the user's mandate", "tone": "allowed"}
    if not failing and decision.get("settlement_error"):
        return {"headline": f"All checks passed, but the rail refused settlement ({decision['settlement_error']}). "
                            "No money moved.", "liability": "User not liable", "tone": "blocked"}
    nums = ", ".join(map(str, failing))
    if 1 in failing:
        head = f"Request was not signed by Asha's registered agent (check{'s' if len(failing) > 1 else ''} {nums})."
    elif failing == [6] and revoked_at:
        head = "Asha had revoked the mandate before this request (check 6)."
    else:
        head = f"Agent exceeded mandate (check{'s' if len(failing) > 1 else ''} {nums})."
    return {"headline": f"{head} Blocked before settlement. User not liable.",
            "liability": "User not liable", "tone": "blocked"}
