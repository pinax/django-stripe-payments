import stripe

from .. import models, utils


def sync_plans():
    """
    Synchronizes all plans from the Stripe API
    """
    plans = stripe.Plan.auto_paging_iter()
    for plan in plans:
        sync_plan(plan)


def sync_plan(plan, event=None):
    """
    Synchronizes a plan from the Stripe API

    Args:
        plan: data from Stripe API representing a plan
        event: the event associated with the plan
    """

    defaults = {
        "amount": utils.convert_amount_for_db(plan["amount"], plan["currency"]),
        "currency": plan["currency"] or "",
        "interval": plan["interval"],
        "interval_count": plan["interval_count"],
        "name": plan["name"],
        "statement_descriptor": plan["statement_descriptor"] or "",
        "trial_period_days": plan["trial_period_days"],
        "metadata": plan["metadata"],
        "billing_scheme": plan["billing_scheme"],
        "tiers_mode": plan["tiers_mode"]
    }

    obj, created = models.Plan.objects.get_or_create(
        stripe_id=plan["id"],
        defaults=defaults
    )
    utils.update_with_defaults(obj, defaults, created)

    if plan["tiers"]:
        obj.tiers.all().delete()    # delete all tiers, since they don't have ids in Stripe
        for tier in plan["tiers"]:
            tier_obj = models.Tier.objects.create(
                plan=obj,
                amount=utils.convert_amount_for_db(tier["amount"], plan["currency"]),
                flat_amount=utils.convert_amount_for_db(tier["flat_amount"], plan["currency"]),
                up_to=tier["up_to"]
            )
            obj.tiers.add(tier_obj)
