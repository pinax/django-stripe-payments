import datetime
import decimal

from django.test import TestCase
from django.utils import timezone


from . import TRANSFER_CREATED_TEST_DATA, TRANSFER_CREATED_TEST_DATA2
from ..managers import get_range
from ..models import Event, Transfer, Customer, CurrentSubscription
from ..settings import User


class CustomerManagerTest(TestCase):
    
    def setUp(self):
        # create customers and current subscription records
        period_start = datetime.datetime(2013, 4, 1, tzinfo=timezone.utc)
        period_end = datetime.datetime(2013, 4, 30, tzinfo=timezone.utc)
        start = datetime.datetime(2013, 1, 1, tzinfo=timezone.utc)
        for i in range(10):
            customer = Customer.objects.create(
                user=User.objects.create_user(username="patrick{0}".format(i)),
                stripe_id="cus_xxxxxxxxxxxxxx{0}".format(i),
                card_fingerprint="YYYYYYYY",
                card_last_4="2342",
                card_kind="Visa"
            )
            CurrentSubscription.objects.create(
                customer=customer,
                plan="test",
                current_period_start=period_start,
                current_period_end=period_end,
                amount=(500 / decimal.Decimal("100.0")),
                status="active",
                start=start,
                quantity=1
            )
        customer = Customer.objects.create(
            user=User.objects.create_user(username="patrick{0}".format(11)),
            stripe_id="cus_xxxxxxxxxxxxxx{0}".format(11),
            card_fingerprint="YYYYYYYY",
            card_last_4="2342",
            card_kind="Visa"
        )
        CurrentSubscription.objects.create(
            customer=customer,
            plan="test",
            current_period_start=period_start,
            current_period_end=period_end,
            amount=(500 / decimal.Decimal("100.0")),
            status="canceled",
            canceled_at=period_end,
            start=start,
            quantity=1
        )
        customer = Customer.objects.create(
            user=User.objects.create_user(username="patrick{0}".format(12)),
            stripe_id="cus_xxxxxxxxxxxxxx{0}".format(12),
            card_fingerprint="YYYYYYYY",
            card_last_4="2342",
            card_kind="Visa"
        )
        CurrentSubscription.objects.create(
            customer=customer,
            plan="test-2",
            current_period_start=period_start,
            current_period_end=period_end,
            amount=(500 / decimal.Decimal("100.0")),
            status="active",
            start=start,
            quantity=1
        )
        # create a December customer and current subscription records
        period_start = datetime.datetime(2013, 12, 1, tzinfo=timezone.utc)
        period_end = datetime.datetime(2013, 12, 31, tzinfo=timezone.utc)
        start = datetime.datetime(2013, 12, 1, tzinfo=timezone.utc)
        customer = Customer.objects.create(
            user=User.objects.create_user(username="patrick{0}".format(13)),
            stripe_id="cus_xxxxxxxxxxxxxx{0}".format(13),
            card_fingerprint="YYYYYYYY",
            card_last_4="2342",
            card_kind="Visa"
        )
        CurrentSubscription.objects.create(
            customer=customer,
            plan="test",
            current_period_start=period_start,
            current_period_end=period_end,
            amount=(500 / decimal.Decimal("100.0")),
            status="active",
            start=start,
            quantity=1
        )
    
    def test_started_during_no_records(self):
        self.assertEqual(
            Customer.objects.started_during(2013, 4).count(),
            0
        )
    
    def test_started_during_has_records(self):
        self.assertEqual(
            Customer.objects.started_during(2013, 1).count(),
            12
        )
    
    def test_started_during_december_has_records(self):
        self.assertEqual(
            Customer.objects.started_during(2013, 12).count(),
            1
        )
    
    def test_canceled_during(self):
        self.assertEqual(
            Customer.objects.canceled_during(2013, 4).count(),
            1
        )
    
    def test_canceled_all(self):
        self.assertEqual(
            Customer.objects.canceled().count(),
            1
        )
    
    def test_active_all(self):
        self.assertEqual(
            Customer.objects.active().count(),
            12
        )
    
    def test_started_plan_summary(self):
        for plan in Customer.objects.started_plan_summary_for(2013, 1):
            if plan["current_subscription__plan"] == "test":
                self.assertEqual(plan["count"], 11)
            if plan["current_subscription__plan"] == "test-2":
                self.assertEqual(plan["count"], 1)
    
    def test_active_plan_summary(self):
        for plan in Customer.objects.active_plan_summary():
            if plan["current_subscription__plan"] == "test":
                self.assertEqual(plan["count"], 11)
            if plan["current_subscription__plan"] == "test-2":
                self.assertEqual(plan["count"], 1)
    
    def test_canceled_plan_summary(self):
        for plan in Customer.objects.canceled_plan_summary_for(2013, 1):
            if plan["current_subscription__plan"] == "test":
                self.assertEqual(plan["count"], 1)
            if plan["current_subscription__plan"] == "test-2":
                self.assertEqual(plan["count"], 0)
    
    def test_churn(self):
        self.assertEqual(
            Customer.objects.churn(),
            decimal.Decimal("1") / decimal.Decimal("12")
        )


class TransferManagerTest(TestCase):
    
    def test_transfer_summary(self):
        event = Event.objects.create(
            stripe_id=TRANSFER_CREATED_TEST_DATA["id"],
            kind="transfer.created",
            livemode=True,
            webhook_message=TRANSFER_CREATED_TEST_DATA,
            validated_message=TRANSFER_CREATED_TEST_DATA,
            valid=True
        )
        event.process()
        event = Event.objects.create(
            stripe_id=TRANSFER_CREATED_TEST_DATA2["id"],
            kind="transfer.created",
            livemode=True,
            webhook_message=TRANSFER_CREATED_TEST_DATA2,
            validated_message=TRANSFER_CREATED_TEST_DATA2,
            valid=True
        )
        event.process()
        self.assertEqual(Transfer.objects.during(2012, 9).count(), 2)
        totals = Transfer.objects.paid_totals_for(2012, 9)
        self.assertEqual(
            totals["total_amount"], decimal.Decimal("19.10")
        )
        self.assertEqual(
            totals["total_net"], decimal.Decimal("19.10")
        )
        self.assertEqual(
            totals["total_charge_fees"], decimal.Decimal("0.90")
        )
        self.assertEqual(
            totals["total_adjustment_fees"], decimal.Decimal("0")
        )
        self.assertEqual(
            totals["total_refund_fees"], decimal.Decimal("0")
        )
        self.assertEqual(
            totals["total_validation_fees"], decimal.Decimal("0")
        )


class FunctionTest(TestCase):
    def test_march(self):
        start_date = timezone.datetime(2013, 3, 1, tzinfo=timezone.utc)
        end_date = timezone.datetime(2013, 4, 1, tzinfo=timezone.utc)
        self.assertEqual(
            get_range(2013, 3),
            (start_date, end_date)
        )
    # pylint: disable-msg=E0611
    def test_december(self):
        start_date = timezone.datetime(2013, 12, 1, tzinfo=timezone.utc)
        end_date = timezone.datetime(2014, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(
            get_range(2013, 12),  # function tested
            (start_date, end_date)  # test value
        )
