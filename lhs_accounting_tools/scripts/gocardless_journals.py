import os
import click
import gocardless_pro
import pytz
import csv
from dateutil.parser import parse as parse_datetime
from datetime import date, timedelta
from collections import defaultdict


def parse_date(date_str):
    # Not using dateutil here as sometimes it thinks you've got an
    # American date format when you haven't.
    return date(*map(int, date_str.split("-")))


def last_day_of_month(year, month):
    next_month = date(year, month, 28) + timedelta(days=4)
    return next_month - timedelta(days=next_month.day)


# Field names for Xero's manual journal import feature
CSV_FIELDS = [
    "*Narration",
    "*Date",
    "Description",
    "*AccountCode",
    "*TaxRate",
    "*Amount",
    "TrackingName1",
    "TrackingOption1",
    "TrackingName2",
    "TrackingOption2",
]

# Account names which must match up with the chart of accounts
FEES_ACCOUNT = "404"
MEMBERSHIP_ACCOUNT = "201"
DONATIONS_ACCOUNT = "200"
CLEARING_ACCOUNT = "GOCARDLESS"


@click.command()
@click.option(
    "--from-date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
    help="Date to start fetching transactions from (inclusive)",
)
@click.option(
    "--until-date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
    help="Date to fetch transactions until (inclusive)",
)
@click.option(
    "--min-membership",
    default=5,
    help="Mandatory minimum membership fee (£)",
    show_default=True,
)
@click.option(
    "--access-token",
    default=lambda: os.environ.get("GOCARDLESS_ACCESS_TOKEN"),
    required=True,
    help="GoCardless API read only access token (can also be provided through the "
    "GOCARDLESS_ACCESS_TOKEN environment variable).",
)
@click.argument("output_csv", type=click.File("w"))
def main(from_date, until_date, min_membership, access_token, output_csv):
    """
        Fetch transactions from the GoCardless API and emit a CSV file of
        manual journals (one per month) for import into Xero.
    """
    from_date = from_date.replace(tzinfo=pytz.utc)
    until_date = until_date.replace(tzinfo=pytz.utc)

    gc = gocardless_pro.Client(access_token=access_token, environment="live")

    payment_data = get_payment_data(gc, from_date, until_date)

    csvfile = csv.writer(output_csv)
    csvfile.writerow(CSV_FIELDS)
    for row in generate_transactions(payment_data, min_membership):
        row_prefix = [
            f"GoCardless membership payments for {row['date'].year}-{row['date'].month}",
            row["date"].isoformat(),
        ]
        continuation = ["", ""]
        csvfile.writerow(
            row_prefix
            + [
                "GoCardless",
                CLEARING_ACCOUNT,
                "No VAT",
                (row["membership"] + row["donations"] - row["fees"]) / 100,
            ]
        )
        csvfile.writerow(
            continuation + ["GoCardless fees", FEES_ACCOUNT, "No VAT", row["fees"] / 100]
        )
        csvfile.writerow(
            continuation
            + [
                "GoCardless membership subscriptions",
                MEMBERSHIP_ACCOUNT,
                "No VAT",
                -row["membership"] / 100,
            ]
        )
        csvfile.writerow(
            continuation
            + ["GoCardless membership donations", DONATIONS_ACCOUNT, "No VAT", -row["donations"] / 100]
        )


def generate_transactions(data, min_membership):
    for (year, month), row in data.items():
        fees_total = sum(row["fees"])
        membership_total = 0
        donation_total = 0
        for amount in row["payments"]:
            if amount < min_membership * 100:
                donation_total += amount
            else:
                membership_total += min_membership * 100
                donation_total += amount - (min_membership * 100)
        yield {
            "date": last_day_of_month(year, month),
            "fees": fees_total,
            "membership": membership_total,
            "donations": donation_total,
        }


def get_payment_data(gc, since_date, until_date):
    data = defaultdict(lambda: {"fees": [], "payments": []})

    for payment in gc.payments.all(
        params={
            "charge_date[gte]": since_date.date().isoformat(),
            "charge_date[lte]": until_date.date().isoformat(),
        }
    ):
        if payment.status not in ("confirmed", "paid_out"):
            continue
        assert payment.currency == "GBP"

        charge_date = parse_date(payment.charge_date)

        data[(charge_date.year, charge_date.month)]["payments"].append(payment.amount)

    for payout in gc.payouts.all(
        params={
            "created_at[gte]": since_date.isoformat(),
            "created_at[lte]": until_date.isoformat(),
        }
    ):
        if payout.status not in ("paid"):
            continue

        assert payout.currency == "GBP"
        created_at = parse_datetime(payout.created_at)

        data[(created_at.year, created_at.month)]["fees"].append(payout.deducted_fees)

    return data
