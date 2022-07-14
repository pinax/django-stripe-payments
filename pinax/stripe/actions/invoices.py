import decimal

import stripe
from django.core.exceptions import MultipleObjectsReturned
from django.utils.encoding import smart_str

from . import charges, subscriptions
from .. import hooks, models, utils
from ..conf import settings


def create(customer, **params):
    """
    Creates a Stripe invoice

    Args:
        customer: the customer to create the invoice for (Customer)

    Returns:
        the data from the Stripe API that represents the invoice object that
        was created

    TODO:
        We should go ahead and sync the data so the Invoice object does
        not have to wait on the webhook to be received and processed for the
        data to be available locally.
    """
    return stripe.Invoice.create(customer=customer.stripe_id, **params)


def retrieve(invoice_id):

    if not invoice_id:
        return

    try:
        return stripe.Invoice.retrieve(invoice_id)
    except stripe.InvalidRequestError as e:
        if smart_str(e).find("No such invoice") == -1:
            raise
        else:
            # Not Found
            return None

def create_and_pay(customer):
    """
    Creates and immediately pays an invoice for a customer

    Args:
        customer: the customer to create the invoice for (Customer)

    Returns:
        True, if invoice was created, False if there was an error
    """

    try:
        invoice = create(customer)
        if invoice.amount_due > 0:
            invoice.pay()
        return True
    except stripe.InvalidRequestError as e:
        if smart_str(e).endswith("Nothing to invoice for customer"):
            return False  # There was nothing to Invoice
        else:
            raise e


def pay(invoice, send_receipt=True):
    """
    Cause an invoice to be paid

    Args:
        invoice: the invoice object to have paid
        send_receipt: if True, send the receipt as a result of paying

    Returns:
        True if the invoice was paid, False if it was unable to be paid
    """
    if not invoice.paid and not invoice.closed:
        stripe_invoice = invoice.stripe_invoice.pay()
        sync_invoice_from_stripe_data(stripe_invoice, send_receipt=send_receipt)
        return True
    return False


def sync_invoice_from_stripe_data(stripe_invoice, send_receipt=settings.PINAX_STRIPE_SEND_EMAIL_RECEIPTS):
    """
    Synchronizes a local invoice with data from the Stripe API

    Args:
        stripe_invoice: data that represents the invoice from the Stripe API
        send_receipt: if True, send the receipt as a result of paying

    Returns:
        the pinax.stripe.models.Invoice that was created or updated
    """
    c = models.Customer.objects.get(stripe_id=stripe_invoice["customer"])
    period_end = utils.convert_tstamp(stripe_invoice, "period_end")
    period_start = utils.convert_tstamp(stripe_invoice, "period_start")
    date = utils.convert_tstamp(stripe_invoice, "date")
    sub_id = stripe_invoice.get("subscription")
    stripe_account_id = c.stripe_account_stripe_id
    invoice_stripe_id = stripe_invoice.get("id")
    charge_id = stripe_invoice.get("charge")

    if charge_id:
        charge = charges.sync_charge(charge_id, stripe_account=stripe_account_id)
        if send_receipt: hooks.hookset.send_receipt(charge)
    else:
        charge = None

    subscription = None
    try:
        stripe_subscription = subscriptions.retrieve(c, sub_id)
        if stripe_subscription:
            subscription = subscriptions.sync_subscription_from_stripe_data(c, stripe_subscription)
    except stripe.InvalidRequestError:
        pass

    defaults = dict(
        customer=c,
        attempted=stripe_invoice["attempted"],
        attempt_count=stripe_invoice["attempt_count"],
        amount_due=utils.convert_amount_for_db(stripe_invoice["amount_due"], stripe_invoice["currency"]),
        closed=stripe_invoice["closed"],
        paid=stripe_invoice["paid"],
        period_end=period_end,
        period_start=period_start,
        subtotal=utils.convert_amount_for_db(stripe_invoice["subtotal"], stripe_invoice["currency"]),
        tax=utils.convert_amount_for_db(stripe_invoice["tax"], stripe_invoice["currency"]) if stripe_invoice["tax"] is not None else None,
        tax_percent=decimal.Decimal(stripe_invoice["tax_percent"]) if stripe_invoice["tax_percent"] is not None else None,
        total=utils.convert_amount_for_db(stripe_invoice["total"], stripe_invoice["currency"]),
        currency=stripe_invoice["currency"],
        metadata=stripe_invoice["metadata"],
        date=date,
        charge=charge,
        subscription=subscription,
        receipt_number=stripe_invoice["receipt_number"] or "",
    )

    try:
        invoice, created = models.Invoice.objects.get_or_create(
            stripe_id=invoice_stripe_id,
            defaults=defaults
        )
    except MultipleObjectsReturned:
        invoice = models.Invoice.objects.filter(stripe_id=invoice_stripe_id).first()
        created = False

    if charge is not None:
        charge.invoice = invoice
        charge.save()

    invoice = utils.update_with_defaults(invoice, defaults, created)
    sync_invoice_items(invoice, stripe_invoice["lines"].get("data", []))

    return invoice


def sync_invoices_for_customer(customer):
    """
    Synchronizes all invoices for a customer

    Args:
        customer: the customer for whom to synchronize all invoices
    """
    for invoice in customer.stripe_customer.invoices().data:
        sync_invoice_from_stripe_data(invoice, send_receipt=False)


def sync_invoice_items(invoice, items):
    """
    Synchronizes all invoice line items for a particular invoice

    This assumes line items from a Stripe invoice.lines property and not through
    the invoicesitems resource calls. At least according to the documentation
    the data for an invoice item is slightly different between the two calls.

    For example, going through the invoiceitems resource you don't get a "type"
    field on the object.

    Args:
        invoice_: the invoice objects to synchronize
        items: the data from the Stripe API representing the line items
        :param invoice:
    """

    # clear any existing invoice item
    invoice.items.all().delete()

    for item in items:
        period_end = utils.convert_tstamp(item["period"], "end")
        period_start = utils.convert_tstamp(item["period"], "start")

        plan = None
        if item.get("plan"):
            try:
                plan = models.Plan.objects.get(stripe_id=item["plan"]["id"])
            except models.Plan.DoesNotExist:
                pass

        if item["type"] == "subscription":
            if invoice.subscription and invoice.subscription.stripe_id == item["id"]:
                item_subscription = invoice.subscription
            else:
                stripe_subscription = subscriptions.retrieve(
                    invoice.customer,
                    item["id"]
                )
                item_subscription = subscriptions.sync_subscription_from_stripe_data(
                    invoice.customer,
                    stripe_subscription
                ) if stripe_subscription else None
            if plan is None and item_subscription is not None and item_subscription.plan is not None:
                plan = item_subscription.plan
        else:
            item_subscription = None

        defaults = dict(
            amount=utils.convert_amount_for_db(item["amount"], item["currency"]),
            currency=item["currency"],
            proration=item["proration"],
            description=item.get("description") or "",
            line_type=item["type"],
            plan=plan,
            period_start=period_start,
            period_end=period_end,
            quantity=item.get("quantity"),
            subscription=item_subscription
        )
        inv_item, inv_item_created = invoice.items.get_or_create(
            stripe_id=item["id"],
            defaults=defaults
        )
        utils.update_with_defaults(inv_item, defaults, inv_item_created)


def delete_drafted_invoice(invoice_id):

    # monkey patch
    class Invoice(stripe.Invoice, stripe.api_resources.abstract.DeletableAPIResource):
        pass

    try:
        invoice = Invoice.retrieve(invoice_id)
        invoice.delete()
    except stripe.InvalidRequestError as e:
        if smart_str(e).find("No such invoice") == -1:
            raise e
