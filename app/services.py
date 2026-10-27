from app.models import OrderStatus

# =====================================================================
# STATE MACHINE BLUEPRINT
# =====================================================================
# This dictionary maps every single OrderStatus to its strictly allowed 
# next steps. If a transition isn't explicitly listed here, it's blocked.

VALID_TRANSITIONS = {
    OrderStatus.PLACED: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
    OrderStatus.CONFIRMED: [OrderStatus.PICKED_UP, OrderStatus.CANCELLED],
    OrderStatus.PICKED_UP: [OrderStatus.IN_TRANSIT],
    OrderStatus.IN_TRANSIT: [OrderStatus.DELIVERED],
    # Terminal states: Once an order is delivered or cancelled, it can never move again
    OrderStatus.DELIVERED: [],
    OrderStatus.CANCELLED: []
}

def validate_status_transition(current_status, next_status) -> bool:
    """
    Validates logistics lifecycle state progression.
    Extracts raw string values out of Enums to prevent comparison type errors.
    """
    # Force extract string values from SQLAlchemy Enums if passed as objects
    current = current_status.value if hasattr(current_status, 'value') else str(current_status)
    target = next_status.value if hasattr(next_status, 'value') else str(next_status)
    
    # Normalize typography to clean lowercase
    current = current.lower().strip()
    target = target.lower().strip()

    # Define strict production status progression paths
    VALID_TRANSITIONS = {
        "placed": ["assigned", "cancelled"],
        "assigned": ["picked_up", "cancelled"],
        "picked_up": ["delivered", "cancelled"],
        "delivered": [],  # Terminal state
        "cancelled": []   # Terminal state
    }

    # Verify if the current state exists in map and target is an authorized path
    if current in VALID_TRANSITIONS:
        return target in VALID_TRANSITIONS[current]
        
    return False